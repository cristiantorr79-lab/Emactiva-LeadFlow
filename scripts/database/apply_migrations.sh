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
  printf 'postgres_migrations phase=validation operation=compose_mode status=FAIL exit_code=2 error_id=LF015-PG-MODE\n' >&2; exit 2
fi
migration_password_env=(-e POSTGRES_BOOTSTRAP_PASSWORD -e POSTGRES_MIGRATOR_PASSWORD -e POSTGRES_APP_PASSWORD)

fail() {
  printf 'postgres_migrations phase=%s operation=%s status=FAIL exit_code=%s error_id=%s\n' "$1" "$2" "$3" "$4" >&2
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

set +e
bash "$script_dir/sync_database_roles.sh"
rc=$?
set -e
[ "$rc" -eq 0 ] || fail role_sync invoke "$rc" LF015-PG-ROLE-SYNC

capture_quiet db_config_output configuration read LF015-PG-MIGRATION-CONFIG \
  "${compose[@]}" exec -T "$postgres_service" sh -eu -c '
    for name in POSTGRES_DB POSTGRES_BOOTSTRAP_USER POSTGRES_MIGRATOR_USER; do
      eval "value=\${$name:-}"
      [ -n "$value" ] || exit 31
    done
    printf "%s\n%s\n%s\n" "$POSTGRES_DB" "$POSTGRES_BOOTSTRAP_USER" "$POSTGRES_MIGRATOR_USER"
  '
mapfile -t db_config <<< "$db_config_output"
[ "${#db_config[@]}" -eq 3 ] && [ -n "${db_config[0]}" ] && [ -n "${db_config[1]}" ] && [ -n "${db_config[2]}" ] || fail configuration parse 32 LF015-PG-MIGRATION-CONFIG-PARSE
postgres_db=${db_config[0]}
bootstrap_user=${db_config[1]}
migrator_user=${db_config[2]}

psql_command() {
  local user=$1; shift
  "${compose[@]}" exec -T "${migration_password_env[@]}" "$postgres_service" psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$postgres_db" "$@"
}
psql_query() { psql_command "$@" </dev/null; }
psql_file() { local user=$1 file=$2; psql_command "$user" < "$file"; }

capture_quiet ledger_exists migration_state ledger_lookup LF015-PG-LEDGER-LOOKUP psql_query "$migrator_user" -Atc "SELECT to_regclass('leadflow.schema_migrations') IS NOT NULL;"
initial_applied=f
if [ "$ledger_exists" = t ]; then
  capture_quiet initial_applied migration_state initial_lookup LF015-PG-INITIAL-LOOKUP psql_query "$migrator_user" -Atc "SELECT EXISTS(SELECT 1 FROM leadflow.schema_migrations WHERE version='001_initial');"
fi
if [ "$initial_applied" != t ]; then
  run_quiet initial_migration apply_001 LF015-PG-INITIAL-APPLY psql_file "$bootstrap_user" "$repo_root/database/migrations/001_initial.sql"
  run_quiet initial_migration transfer_ownership LF015-PG-OWNERSHIP-TRANSFER psql_file "$bootstrap_user" "$script_dir/transfer_leadflow_ownership.sql"
fi

capture_quiet migration_list_output migration_list discover LF015-PG-MIGRATION-LIST bash -o pipefail -c 'find "$1" -maxdepth 1 -type f -name "*.sql" -print | sort' _ "$repo_root/database/migrations"
mapfile -t migrations <<< "$migration_list_output"
[ "${#migrations[@]}" -gt 0 ] && [ -n "${migrations[0]}" ] || fail migration_list parse 33 LF015-PG-MIGRATION-LIST-EMPTY
expected=0
for migration in "${migrations[@]}"; do
  [ "$(basename "$migration" .sql)" = 001_initial ] || expected=$((expected+1))
done
processed=0
for migration in "${migrations[@]}"; do
  version=$(basename "$migration" .sql)
  [ "$version" != 001_initial ] || continue
  case "$version" in (*[!a-zA-Z0-9_-]*|'') fail migration_list version_name 35 LF015-PG-MIGRATION-NAME ;; esac
  capture_quiet applied subsequent_migrations "lookup_$version" LF015-PG-MIGRATION-LOOKUP psql_query "$migrator_user" -Atc "SELECT EXISTS(SELECT 1 FROM leadflow.schema_migrations WHERE version='$version');"
  if [ "$applied" = t ]; then
    echo "Already applied: $version"
  else
    run_quiet subsequent_migrations "apply_$version" LF015-PG-MIGRATION-APPLY psql_file "$migrator_user" "$migration"
  fi
  processed=$((processed+1))
done
[ "$processed" -eq "$expected" ] || fail subsequent_migrations traversal 34 LF015-PG-MIGRATION-TRAVERSAL

capture_quiet applied_versions migration_verification ledger_read LF015-PG-LEDGER-READ psql_query "$migrator_user" -Atc 'SELECT version FROM leadflow.schema_migrations ORDER BY version;'
[ -z "$applied_versions" ] || printf '%s\n' "$applied_versions"
