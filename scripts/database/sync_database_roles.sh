#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
postgres_service=postgres
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/compose.yaml")
if [ "${POSTGRES_ADMIN_COMPOSE_MODE:-runtime}" = bootstrap ]; then
  compose=(docker compose --project-directory "$repo_root" -f "$repo_root/compose.postgres-bootstrap.yaml")
  postgres_service=postgres-bootstrap
elif [ "${POSTGRES_ADMIN_COMPOSE_MODE:-runtime}" != runtime ]; then
  printf 'postgres_roles phase=validation operation=compose_mode status=FAIL exit_code=2 error_id=LF015-PG-MODE\n' >&2; exit 2
fi
admin_password_env=(-e POSTGRES_BOOTSTRAP_PASSWORD -e POSTGRES_MIGRATOR_PASSWORD -e POSTGRES_APP_PASSWORD)
compose_exec() { "${compose[@]}" exec -T "${admin_password_env[@]}" "$@"; }
fail() {
  printf 'postgres_roles phase=%s operation=%s status=FAIL exit_code=%s error_id=%s\n' "$1" "$2" "$3" "$4" >&2
  exit "$3"
}
capture_quiet() {
  local destination=$1 phase=$2 operation=$3 error_id=$4 value rc
  shift 4
  set +e
  value=$("$@" 2>/dev/null); rc=$?
  set -e
  [ "$rc" -eq 0 ] || fail "$phase" "$operation" "$rc" "$error_id"
  printf -v "$destination" '%s' "$value"
}
run_quiet() {
  local phase=$1 operation=$2 error_id=$3 rc
  shift 3
  set +e
  "$@" >/dev/null 2>&1; rc=$?
  set -e
  [ "$rc" -eq 0 ] || fail "$phase" "$operation" "$rc" "$error_id"
}

capture_quiet role_config_output configuration read LF015-PG-ROLE-CONFIG compose_exec "$postgres_service" sh -eu -c '
  for name in POSTGRES_DB POSTGRES_BOOTSTRAP_USER POSTGRES_BOOTSTRAP_PASSWORD POSTGRES_MIGRATOR_USER POSTGRES_MIGRATOR_PASSWORD POSTGRES_APP_USER POSTGRES_APP_PASSWORD; do
    eval "value=\${$name:-}"
    [ -n "$value" ] || exit 31
  done
  [ "$POSTGRES_BOOTSTRAP_USER" != "$POSTGRES_MIGRATOR_USER" ] &&
  [ "$POSTGRES_BOOTSTRAP_USER" != "$POSTGRES_APP_USER" ] &&
  [ "$POSTGRES_MIGRATOR_USER" != "$POSTGRES_APP_USER" ] || exit 32
  [ "$POSTGRES_BOOTSTRAP_PASSWORD" != "$POSTGRES_MIGRATOR_PASSWORD" ] &&
  [ "$POSTGRES_BOOTSTRAP_PASSWORD" != "$POSTGRES_APP_PASSWORD" ] &&
  [ "$POSTGRES_MIGRATOR_PASSWORD" != "$POSTGRES_APP_PASSWORD" ] || exit 33
  sync_user=${POSTGRES_ROLE_SYNC_USER:-$POSTGRES_BOOTSTRAP_USER}
  [ "$sync_user" = "$POSTGRES_BOOTSTRAP_USER" ] || [ "$sync_user" = "$POSTGRES_MIGRATOR_USER" ] || exit 34
  printf "%s\n%s\n%s\n%s\n" "$POSTGRES_BOOTSTRAP_USER" "$POSTGRES_MIGRATOR_USER" "$POSTGRES_APP_USER" "$sync_user"
'
mapfile -t role_config <<< "$role_config_output"
[ "${#role_config[@]}" -eq 4 ] && [ -n "${role_config[0]}" ] && [ -n "${role_config[1]}" ] && [ -n "${role_config[2]}" ] && [ -n "${role_config[3]}" ] || fail configuration parse 35 LF015-PG-ROLE-CONFIG-PARSE
bootstrap_user=${role_config[0]}
migrator_user=${role_config[1]}
app_user=${role_config[2]}
sync_user=${role_config[3]}
transition_user="${bootstrap_user}_transition"
[ "${#transition_user}" -le 63 ] || fail validation transition_name 36 LF015-PG-TRANSITION-NAME
[ "$transition_user" != "$bootstrap_user" ] && [ "$transition_user" != "$migrator_user" ] && [ "$transition_user" != "$app_user" ] || fail validation transition_conflict 37 LF015-PG-TRANSITION-CONFLICT

capture_quiet postgres_db configuration database_name LF015-PG-DATABASE-NAME compose_exec "$postgres_service" sh -eu -c 'printf "%s" "$POSTGRES_DB"'
[ -n "$postgres_db" ] || fail configuration database_name 38 LF015-PG-DATABASE-NAME-EMPTY
psql_as() {
  local user=$1 sql_file=$2
  compose_exec -e "POSTGRES_TRANSITION_USER=$transition_user" "$postgres_service" psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$postgres_db" < "$sql_file"
}

capture_quiet legacy_state role_topology inspect LF015-PG-ROLE-TOPOLOGY compose_exec -e "POSTGRES_TRANSITION_USER=$transition_user" "$postgres_service" \
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

case "$legacy_state" in
  legacy_prepare|legacy_transfer|legacy_finalize)
    [ "$sync_user" = "$migrator_user" ] || fail role_sync legacy_authorization 39 LF015-PG-LEGACY-AUTH
    if [ "$legacy_state" = legacy_prepare ]; then
      run_quiet role_sync legacy_prepare LF015-PG-LEGACY-PREPARE psql_as "$migrator_user" "$script_dir/sync_database_roles_legacy_prepare.sql"
      legacy_state=legacy_transfer
    fi
    if [ "$legacy_state" = legacy_transfer ]; then
      run_quiet role_sync legacy_transfer LF015-PG-LEGACY-TRANSFER psql_as "$transition_user" "$script_dir/sync_database_roles_legacy_transfer.sql"
      legacy_state=legacy_finalize
    fi
    if [ "$legacy_state" = legacy_finalize ]; then
      run_quiet role_sync legacy_finalize LF015-PG-LEGACY-FINALIZE psql_as "$bootstrap_user" "$script_dir/sync_database_roles_legacy_finalize.sql"
    fi
    ;;
  normal) run_quiet role_sync normal LF015-PG-ROLE-SYNC-NORMAL psql_as "$sync_user" "$script_dir/sync_database_roles.sql" ;;
  *) fail role_topology unsupported 40 LF015-PG-ROLE-TOPOLOGY-UNSUPPORTED ;;
esac

echo 'PostgreSQL roles synchronized'
