#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
compose=(docker compose --project-directory "$repo_root" -f "$repo_root/compose.postgres-bootstrap.yaml")
service=postgres-bootstrap
started=false

diagnostic() {
  printf 'postgres_bootstrap phase=%s operation=%s status=FAIL exit_code=%s error_id=%s\n' "$1" "$2" "$3" "$4" >&2
}
fail() { diagnostic "$1" "$2" "$3" "$4"; exit "$3"; }
cleanup() {
  local original_rc=$1 stop_rc=0 rm_rc=0 final_rc=$1
  if [ "$started" = true ]; then
    set +e
    "${compose[@]}" stop "$service" >/dev/null 2>&1; stop_rc=$?
    "${compose[@]}" rm -f "$service" >/dev/null 2>&1; rm_rc=$?
    set -e
    if [ "$stop_rc" -ne 0 ]; then
      diagnostic cleanup stop_container "$stop_rc" LF015-PG-CLEANUP-STOP
      [ "$final_rc" -ne 0 ] || final_rc=$stop_rc
    fi
    if [ "$rm_rc" -ne 0 ]; then
      diagnostic cleanup remove_container "$rm_rc" LF015-PG-CLEANUP-RM
      [ "$final_rc" -ne 0 ] || final_rc=$rm_rc
    fi
    started=false
  fi
  return "$final_rc"
}
on_exit() {
  local rc=$?
  trap - EXIT
  set +e
  cleanup "$rc"
  rc=$?
  set -e
  exit "$rc"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

[ "${LEADFLOW_POSTGRES_BOOTSTRAP_AUTHORIZED:-}" = true ] || fail authorization verify 20 LF015-PG-AUTH-REQUIRED
[ -n "${COMPOSE_PROJECT_NAME:-}" ] || fail validation compose_project 21 LF015-PG-PROJECT-REQUIRED
case "$COMPOSE_PROJECT_NAME" in (*[!a-zA-Z0-9_-]*|'') fail validation compose_project 22 LF015-PG-PROJECT-INVALID ;; esac
export COMPOSE_DISABLE_ENV_FILE=1 APP_ENV=production

for name in POSTGRES_DB POSTGRES_BOOTSTRAP_USER POSTGRES_BOOTSTRAP_PASSWORD POSTGRES_MIGRATOR_USER POSTGRES_MIGRATOR_PASSWORD POSTGRES_APP_USER POSTGRES_APP_PASSWORD; do
  [ -n "${!name:-}" ] || fail validation required_configuration 23 LF015-PG-CONFIG-INCOMPLETE
done
set +e
python3 "$repo_root/scripts/validation/validate_deployment_config.py" --context postgres-admin >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] || fail validation postgres_admin_contract "$rc" LF015-PG-CONFIG-INVALID

set +e
"${compose[@]}" run --rm --no-deps --entrypoint sh "$service" -eu -c '
  data=/var/lib/postgresql/data
  entries=$(find "$data" -mindepth 1 -maxdepth 1 -print -quit)
  if [ -z "$entries" ]; then exit 10; fi
  if [ -f "$data/PG_VERSION" ] && [ -d "$data/base" ] && [ -d "$data/global" ]; then exit 11; fi
  exit 12
' >/dev/null 2>&1
state=$?
set -e
case "$state" in
  10) ;;
  11) fail volume_classification inspect 11 LF015-PG-VOLUME-INITIALIZED ;;
  12) fail volume_classification inspect 12 LF015-PG-VOLUME-AMBIGUOUS ;;
  *) fail volume_classification inspect "$state" LF015-PG-VOLUME-INSPECT ;;
esac

started=true
set +e
"${compose[@]}" up -d "$service" >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 0 ] || fail postgres_start compose_up "$rc" LF015-PG-START

set +e
container_id=$("${compose[@]}" ps -q "$service" 2>/dev/null)
rc=$?
set -e
[ "$rc" -eq 0 ] || fail postgres_start container_lookup "$rc" LF015-PG-CONTAINER-LOOKUP
[ -n "$container_id" ] || fail postgres_start container_lookup 24 LF015-PG-CONTAINER-MISSING

healthy=false
for _ in $(seq 1 60); do
  set +e
  status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null)
  rc=$?
  set -e
  [ "$rc" -eq 0 ] || fail postgres_health inspect "$rc" LF015-PG-HEALTH-INSPECT
  case "$status" in
    healthy) healthy=true; break ;;
    unhealthy|exited|dead) fail postgres_health wait 25 LF015-PG-NOT-HEALTHY ;;
    starting|created|running) ;;
    *) fail postgres_health inspect 26 LF015-PG-HEALTH-STATE ;;
  esac
  sleep 1
done
[ "$healthy" = true ] || fail postgres_health wait 27 LF015-PG-HEALTH-TIMEOUT

set +e
POSTGRES_ADMIN_COMPOSE_MODE=bootstrap bash "$script_dir/apply_migrations.sh" >/dev/null
rc=$?
set -e
[ "$rc" -eq 0 ] || fail migrations apply "$rc" LF015-PG-MIGRATIONS

trap - EXIT
set +e
cleanup 0
rc=$?
set -e
[ "$rc" -eq 0 ] || exit "$rc"
echo 'PostgreSQL bootstrap: PASS'
