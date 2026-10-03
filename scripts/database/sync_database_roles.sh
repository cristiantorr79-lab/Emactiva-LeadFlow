#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/compose.yaml")

mapfile -t role_config < <("${compose[@]}" exec -T postgres sh -eu -c '
  for name in POSTGRES_DB POSTGRES_BOOTSTRAP_USER POSTGRES_BOOTSTRAP_PASSWORD POSTGRES_MIGRATOR_USER POSTGRES_MIGRATOR_PASSWORD POSTGRES_APP_USER POSTGRES_APP_PASSWORD; do
    eval "value=\${$name:-}"
    [ -n "$value" ] || { echo "Required PostgreSQL container variable is missing: $name" >&2; exit 1; }
  done
  [ "$POSTGRES_BOOTSTRAP_USER" != "$POSTGRES_MIGRATOR_USER" ] &&
  [ "$POSTGRES_BOOTSTRAP_USER" != "$POSTGRES_APP_USER" ] &&
  [ "$POSTGRES_MIGRATOR_USER" != "$POSTGRES_APP_USER" ] || { echo "PostgreSQL role names must be distinct" >&2; exit 1; }
  [ "$POSTGRES_BOOTSTRAP_PASSWORD" != "$POSTGRES_MIGRATOR_PASSWORD" ] &&
  [ "$POSTGRES_BOOTSTRAP_PASSWORD" != "$POSTGRES_APP_PASSWORD" ] &&
  [ "$POSTGRES_MIGRATOR_PASSWORD" != "$POSTGRES_APP_PASSWORD" ] || { echo "PostgreSQL role passwords must be distinct" >&2; exit 1; }
  sync_user=${POSTGRES_ROLE_SYNC_USER:-$POSTGRES_BOOTSTRAP_USER}
  [ "$sync_user" = "$POSTGRES_BOOTSTRAP_USER" ] || [ "$sync_user" = "$POSTGRES_MIGRATOR_USER" ] || { echo "POSTGRES_ROLE_SYNC_USER is not allowed" >&2; exit 1; }
  printf "%s\n%s\n%s\n%s\n" "$POSTGRES_BOOTSTRAP_USER" "$POSTGRES_MIGRATOR_USER" "$POSTGRES_APP_USER" "$sync_user"
')

[ "${#role_config[@]}" -eq 4 ] || { echo 'Could not read PostgreSQL role configuration' >&2; exit 1; }
bootstrap_user=${role_config[0]}
migrator_user=${role_config[1]}
app_user=${role_config[2]}
sync_user=${role_config[3]}
transition_user="${bootstrap_user}_transition"
[ "${#transition_user}" -le 63 ] || { echo 'Derived PostgreSQL transition role name is too long' >&2; exit 1; }
[ "$transition_user" != "$bootstrap_user" ] && [ "$transition_user" != "$migrator_user" ] && [ "$transition_user" != "$app_user" ] || {
  echo 'Derived PostgreSQL transition role name conflicts with an operational role' >&2; exit 1;
}

# Database name is read without exposing secrets; Compose already loaded .env.
postgres_db=$("${compose[@]}" exec -T postgres sh -eu -c 'printf "%s" "$POSTGRES_DB"')
psql_as() {
  local user=$1 sql_file=$2
  "${compose[@]}" exec -T -e "POSTGRES_TRANSITION_USER=$transition_user" postgres \
    psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$postgres_db" < "$sql_file"
}

legacy_state=$("${compose[@]}" exec -T -e "POSTGRES_TRANSITION_USER=$transition_user" postgres \
  psql -X -q -v ON_ERROR_STOP=1 -U "$sync_user" -d "$postgres_db" -At <<'SQL'
\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv migrator_user POSTGRES_MIGRATOR_USER
\getenv transition_user POSTGRES_TRANSITION_USER
SELECT CASE
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'migrator_user') IS TRUE
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'legacy_prepare'
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'migrator_user') IS TRUE
  AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'legacy_transfer'
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'bootstrap_user') IS TRUE
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'migrator_user')
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'legacy_finalize'
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'migrator_user') IS TRUE
   OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'unsupported'
 ELSE 'normal' END;
SQL
)

case "$legacy_state" in
  legacy_prepare|legacy_transfer|legacy_finalize)
    [ "$sync_user" = "$migrator_user" ] || { echo 'Legacy OID 10 repair must start with POSTGRES_ROLE_SYNC_USER set to the historical migrator' >&2; exit 1; }
    if [ "$legacy_state" = legacy_prepare ]; then
      psql_as "$migrator_user" "$script_dir/sync_database_roles_legacy_prepare.sql"
      legacy_state=legacy_transfer
    fi
    if [ "$legacy_state" = legacy_transfer ]; then
      psql_as "$transition_user" "$script_dir/sync_database_roles_legacy_transfer.sql"
      legacy_state=legacy_finalize
    fi
    if [ "$legacy_state" = legacy_finalize ]; then
      psql_as "$bootstrap_user" "$script_dir/sync_database_roles_legacy_finalize.sql"
    fi
    ;;
  normal) psql_as "$sync_user" "$script_dir/sync_database_roles.sql" ;;
  *) echo "Unsupported PostgreSQL role topology: $legacy_state" >&2; exit 1 ;;
esac

echo 'PostgreSQL roles synchronized'
