#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP=""
PREPARE_PARTIAL=0
die() { printf 'qa_probe phase=%s status=FAIL\n' "${1:-preflight}" >&2; exit 1; }
cleanup_tmp() {
  status=$?
  if [[ "$status" != 0 && "$PREPARE_PARTIAL" == 1 ]]; then rollback_prepare >/dev/null 2>&1 || status=1; fi
  [[ -z "$TMP" ]] || rm -rf -- "$TMP" || status=1
  exit "$status"
}
trap cleanup_tmp EXIT

for command in docker python3 sha256sum; do command -v "$command" >/dev/null || die preflight; done
ACTION="${1:-}"; RUN_ID="${2:-}"
[[ "$ACTION" == prepare || "$ACTION" == verify || "$ACTION" == cleanup || "$ACTION" == inspect ]] || die action
[[ "$RUN_ID" =~ ^lf015-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] || die run_id
[[ -n "${LF015_QA_COMPOSE_PROJECT:-}" && "$LF015_QA_COMPOSE_PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die compose_project
[[ -n "${LF015_QA_AUTHORIZED_PROJECT:-}" && "$LF015_QA_COMPOSE_PROJECT" == "$LF015_QA_AUTHORIZED_PROJECT" ]] || die compose_project
[[ "${LF015_QA_COMPOSE_OVERRIDE:-}" == /* && -f "$LF015_QA_COMPOSE_OVERRIDE" && -r "$LF015_QA_COMPOSE_OVERRIDE" ]] || die compose_override
[[ -n "${POSTGRES_DB:-}" && -n "${POSTGRES_APP_USER:-}" && -n "${POSTGRES_BOOTSTRAP_USER:-}" ]] || die postgres_config

TMP="$(mktemp -d "${TMPDIR:-/tmp}/lf015-qa-probe.XXXXXXXX")"; chmod 700 "$TMP"
COMPOSE=(docker compose -p "$LF015_QA_COMPOSE_PROJECT" -f "$ROOT/compose.yaml" -f "$LF015_QA_COMPOSE_OVERRIDE")
"${COMPOSE[@]}" config --format json >"$TMP/compose.json" || die compose_config
python3 - "$TMP/compose.json" <<'PY' || die isolation
import json,sys
c=json.load(open(sys.argv[1],encoding="utf-8")); services=c.get("services",{}); networks=c.get("networks",{})
assert {"postgres","n8n"}.issubset(services)
assert not services["postgres"].get("ports") and not services["n8n"].get("ports")
p=set(services["postgres"].get("networks",{})); n=set(services["n8n"].get("networks",{})); shared=p & n
assert shared and all(networks.get(name,{}).get("internal") is True for name in p | n)
PY

N8N_ID="$("${COMPOSE[@]}" ps -q n8n)"; POSTGRES_ID="$("${COMPOSE[@]}" ps -q postgres)"
[[ -n "$N8N_ID" && "$N8N_ID" != *$'\n'* && -n "$POSTGRES_ID" && "$POSTGRES_ID" != *$'\n'* ]] || die compose_services
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' "$N8N_ID")" == "$LF015_QA_COMPOSE_PROJECT|n8n" ]] || die isolation
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' "$POSTGRES_ID")" == "$LF015_QA_COMPOSE_PROJECT|postgres" ]] || die isolation
for spec in "$N8N_ID|/home/node/.n8n" "$POSTGRES_ID|/var/lib/postgresql/data"; do
  container="${spec%%|*}"; destination="${spec#*|}"
  mount="$(docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$destination\"}}{{.Type}}|{{.Name}}{{end}}{{end}}" "$container")"
  [[ "$mount" == volume\|* ]] || die volume
  [[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "${mount#volume|}")" == "$LF015_QA_COMPOSE_PROJECT" ]] || die volume
done

PROBE_PATH="/home/node/.n8n/lf015-probes/$RUN_ID.json"
SOURCE="lf015_qa_probe"; EXECUTION_ID="probe-$RUN_ID"
IDEMPOTENCY_KEY="$(printf '%s' "$SOURCE:$RUN_ID" | sha256sum | awk '{print $1}')"
LEAD_IDENTIFIER="$(printf '%s' "lead:$RUN_ID" | sha256sum | awk '{print $1}')"
SUBJECT_TOKEN="$(printf '%s' "subject:$RUN_ID" | sha256sum | awk '{print $1}')"
printf '{"format":"LF015-QA-PROBE-1","run_id":"%s"}\n' "$RUN_ID" >"$TMP/probe.json"
EXPECTED_SHA="$(sha256sum "$TMP/probe.json" | awk '{print $1}')"
postgres_verify() {
  "${COMPOSE[@]}" exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_BOOTSTRAP_USER" -d "$POSTGRES_DB" -At \
    -v execution_id="$EXECUTION_ID" -v idempotency_key="$IDEMPOTENCY_KEY" -v lead_identifier="$LEAD_IDENTIFIER" -v subject_token="$SUBJECT_TOKEN" <<'SQL'
SELECT
 (SELECT count(*) FROM leadflow.executions WHERE execution_id=:'execution_id' AND source='lf015_qa_probe' AND idempotency_key=:'idempotency_key' AND lead_identifier=:'lead_identifier' AND subject_token=:'subject_token')||'|'||
 (SELECT count(*) FROM leadflow.execution_events WHERE execution_id=:'execution_id' AND (status,stage) IN (('received','validation'),('processing','idempotency')))||'|'||
 (SELECT count(*) FROM leadflow.execution_events WHERE execution_id=:'execution_id');
SQL
}
n8n_sha() { docker exec "$N8N_ID" sha256sum "$PROBE_PATH" 2>/dev/null | awk '{print $1}'; }
postgres_delete() {
  "${COMPOSE[@]}" exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_BOOTSTRAP_USER" -d "$POSTGRES_DB" -At \
    -v execution_id="$EXECUTION_ID" -v idempotency_key="$IDEMPOTENCY_KEY" -v lead_identifier="$LEAD_IDENTIFIER" -v subject_token="$SUBJECT_TOKEN" <<'SQL'
WITH owned AS MATERIALIZED (
  SELECT e.execution_id FROM leadflow.executions e
  WHERE e.execution_id=:'execution_id' AND e.source='lf015_qa_probe' AND e.idempotency_key=:'idempotency_key'
    AND e.lead_identifier=:'lead_identifier' AND e.subject_token=:'subject_token'
    AND (SELECT count(*) FROM leadflow.execution_events x WHERE x.execution_id=e.execution_id)=2
    AND (SELECT count(*) FROM leadflow.execution_events x WHERE x.execution_id=e.execution_id AND (x.status,x.stage) IN (('received','validation'),('processing','idempotency')))=2
), events AS (
  DELETE FROM leadflow.execution_events x USING owned o WHERE x.execution_id=o.execution_id RETURNING 1
), execution AS (
  DELETE FROM leadflow.executions e USING owned o
  WHERE e.execution_id=o.execution_id AND (SELECT count(*) FROM events)=2
  RETURNING 1
) SELECT (SELECT count(*) FROM events)||'|'||(SELECT count(*) FROM execution);
SQL
}
remove_n8n_probe() {
  docker exec "$N8N_ID" sh -eu -c 'path=$1; if test -e "$path"; then test -f "$path"; rm -- "$path"; fi; rmdir "${path%/*}" 2>/dev/null || true; test ! -e "$path"' sh "$PROBE_PATH"
}
rollback_prepare() { result="$(postgres_delete)"; [[ "$result" == "0|0" || "$result" == "2|1" ]] && remove_n8n_probe; }

case "$ACTION" in
  inspect)
    state="$(postgres_verify)"; [[ "$state" == "0|0|0" || "$state" == "1|2|2" ]] || die inspect
    probe_sha="$(n8n_sha || true)"; [[ -z "$probe_sha" || "$probe_sha" =~ ^[0-9a-f]{64}$ ]] || die inspect
    [[ -n "$probe_sha" ]] || probe_sha=ABSENT
    printf 'qa_probe run_id=%s postgres=%s n8n_sha256=%s status=INSPECTED\n' "$RUN_ID" "$state" "$probe_sha"
    ;;
  prepare)
    [[ "$(postgres_verify)" == "0|0|0" ]] || die collision
    PREPARE_PARTIAL=1
    CLAIM_RESULT="$("${COMPOSE[@]}" exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_APP_USER" -d "$POSTGRES_DB" -At \
      -v execution_id="$EXECUTION_ID" -v event_id="$RUN_ID" -v idempotency_key="$IDEMPOTENCY_KEY" -v lead_identifier="$LEAD_IDENTIFIER" -v subject_token="$SUBJECT_TOKEN" <<'SQL'
SELECT (CASE WHEN claimed THEN 't' ELSE 'f' END)||'|'||execution_id||'|'||coalesce(original_execution_id,'') FROM leadflow.claim_event(
  :'execution_id','lf015_qa_probe',:'event_id',
  :'idempotency_key',:'lead_identifier',:'subject_token'
);
SQL
)" || die postgres_prepare
    [[ "$CLAIM_RESULT" == "t|$EXECUTION_ID|" ]] || die postgres_prepare
    docker exec -i "$N8N_ID" sh -eu -c 'path=$1; dir=${path%/*}; mkdir -p "$dir"; test ! -e "$path"; tmp="$path.tmp"; cat >"$tmp"; chmod 600 "$tmp"; mv "$tmp" "$path"' sh "$PROBE_PATH" <"$TMP/probe.json" || die n8n_prepare
    [[ "$(postgres_verify)" == "1|2|2" && "$(n8n_sha)" == "$EXPECTED_SHA" ]] || die prepare_verify
    PREPARE_PARTIAL=0
    printf 'qa_probe run_id=%s postgres=PASS n8n_sha256=%s status=PASS\n' "$RUN_ID" "$EXPECTED_SHA"
    ;;
  verify)
    [[ "$(postgres_verify)" == "1|2|2" ]] || die postgres_verify
    ACTUAL_SHA="$(n8n_sha)"; [[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || die n8n_verify
    printf 'qa_probe run_id=%s postgres=PASS n8n_sha256=%s status=PASS\n' "$RUN_ID" "$ACTUAL_SHA"
    ;;
  cleanup)
    state="$(postgres_verify)"
    [[ "$state" == "0|0|0" || "$state" == "1|2|2" ]] || die cleanup_precondition
    [[ "$state" == "0|0|0" ]] || [[ "$(postgres_delete)" == "2|1" ]] || die postgres_cleanup
    remove_n8n_probe || die n8n_cleanup
    [[ "$(postgres_verify)" == "0|0|0" ]] || die cleanup_verify
    printf 'qa_probe run_id=%s cleanup=PASS status=PASS\n' "$RUN_ID"
    ;;
esac
