#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/compose.yaml")

bash "$script_dir/sync_database_roles.sh"

mapfile -t db_config < <("${compose[@]}" exec -T postgres sh -eu -c '
  for name in POSTGRES_DB POSTGRES_BOOTSTRAP_USER POSTGRES_MIGRATOR_USER; do
    eval "value=\${$name:-}"
    [ -n "$value" ] || { echo "Required PostgreSQL container variable is missing: $name" >&2; exit 1; }
  done
  printf "%s\n%s\n%s\n" "$POSTGRES_DB" "$POSTGRES_BOOTSTRAP_USER" "$POSTGRES_MIGRATOR_USER"
')
[ "${#db_config[@]}" -eq 3 ] || { echo 'Could not read PostgreSQL migration configuration' >&2; exit 1; }
postgres_db=${db_config[0]}
bootstrap_user=${db_config[1]}
migrator_user=${db_config[2]}

psql_command() {
  local user=$1; shift
  "${compose[@]}" exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$user" -d "$postgres_db" "$@"
}
psql_file() {
  local user=$1 file=$2
  psql_command "$user" < "$file"
}

ledger_exists=$(psql_command "$migrator_user" -Atc "SELECT to_regclass('leadflow.schema_migrations') IS NOT NULL;")
initial_applied=f
if [ "$ledger_exists" = t ]; then
  initial_applied=$(psql_command "$migrator_user" -Atc "SELECT EXISTS(SELECT 1 FROM leadflow.schema_migrations WHERE version='001_initial');")
fi
if [ "$initial_applied" != t ]; then
  psql_file "$bootstrap_user" "$repo_root/database/migrations/001_initial.sql"
  psql_file "$bootstrap_user" "$script_dir/transfer_leadflow_ownership.sql"
fi

while IFS= read -r migration; do
  version=$(basename "$migration" .sql)
  [ "$version" != 001_initial ] || continue
  applied=$(psql_command "$migrator_user" -Atc "SELECT EXISTS(SELECT 1 FROM leadflow.schema_migrations WHERE version='$version');")
  if [ "$applied" = t ]; then
    echo "Already applied: $version"
  else
    psql_file "$migrator_user" "$migration"
  fi
done < <(find "$repo_root/database/migrations" -maxdepth 1 -type f -name '*.sql' -print | sort)

psql_command "$migrator_user" -Atc 'SELECT version FROM leadflow.schema_migrations ORDER BY version;'
