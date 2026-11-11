#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="$ROOT/config/backup-policy.json"
TMP=""
N8N_ID=""
N8N_PAUSED=0

log() { printf 'backup phase=%s status=%s\n' "$1" "$2"; }
die() { log "${1:-preflight}" FAIL >&2; exit 1; }
cleanup() {
  status=$?
  if [[ "$N8N_PAUSED" == 1 && -n "$N8N_ID" ]]; then
    paused="$(timeout 10 docker inspect -f '{{.State.Paused}}' "$N8N_ID" 2>/dev/null)" || status=1
    [[ "$paused" != true ]] || timeout 30 docker unpause "$N8N_ID" >/dev/null 2>&1 || status=1
  fi
  [[ -z "$TMP" ]] || rm -rf -- "$TMP" || status=1
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

for command in python3 node docker tar sha256sum curl timeout; do command -v "$command" >/dev/null || die preflight; done
[[ -f "$POLICY" && -n "${BACKUP_KEY_FILE:-}" && -r "$BACKUP_KEY_FILE" ]] || die preflight
[[ -n "${BACKUP_GCS_BUCKET:-}" && "$BACKUP_GCS_BUCKET" =~ ^gs://[^/]+/?$ ]] || die preflight
[[ -n "${BACKUP_COMPOSE_PROJECT:-}" && "$BACKUP_COMPOSE_PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die compose_project
[[ -n "${SOURCE_COMPOSE_PROJECT:-}" && "$SOURCE_COMPOSE_PROJECT" == "$BACKUP_COMPOSE_PROJECT" ]] || die compose_project
[[ "${BACKUP_COMPOSE_OVERRIDE:-}" == /* && -f "$BACKUP_COMPOSE_OVERRIDE" && -r "$BACKUP_COMPOSE_OVERRIDE" ]] || die compose_override
[[ "${BACKUP_PAUSE_TIMEOUT_SECONDS:=1800}" =~ ^[1-9][0-9]*$ ]] && (( BACKUP_PAUSE_TIMEOUT_SECONDS<=3600 )) || die preflight
[[ "${GCS_UPLOAD_TIMEOUT_SECONDS:=300}" =~ ^[1-9][0-9]*$ ]] && (( GCS_UPLOAD_TIMEOUT_SECONDS<=3600 )) || die preflight
[[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -z "${CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE:-}" && -z "${GCE_METADATA_HOST:-}" && -z "${GCE_METADATA_IP:-}" ]] || die preflight
python3 "$ROOT/scripts/validation/validate_backup_policy.py" >/dev/null || die preflight
SERVICE_ACCOUNT_PATTERN='^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]@[a-z0-9][a-z0-9-]{4,61}[a-z0-9]\.iam\.gserviceaccount\.com$'
[[ "${BACKUP_GCP_AUTH_MODE:=attached}" == attached || "$BACKUP_GCP_AUTH_MODE" == impersonation ]] || die identity
[[ "${BACKUP_GCP_IDENTITY:-}" =~ $SERVICE_ACCOUNT_PATTERN ]] || die identity
METADATA_URL="http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
MANAGED_IDENTITY="$(curl --fail --silent --show-error --noproxy '*' --connect-timeout 2 --max-time 5 -H 'Metadata-Flavor: Google' "$METADATA_URL" 2>/dev/null)" || die identity
UPLOAD_AUTH_ARGS=()
if [[ "$BACKUP_GCP_AUTH_MODE" == attached ]]; then
  [[ "$MANAGED_IDENTITY" == "$BACKUP_GCP_IDENTITY" ]] || die identity
else
  [[ "${BACKUP_RUNTIME_GCP_IDENTITY:-}" =~ $SERVICE_ACCOUNT_PATTERN ]] || die identity
  [[ "$BACKUP_RUNTIME_GCP_IDENTITY" != "$BACKUP_GCP_IDENTITY" ]] || die identity
  [[ "$MANAGED_IDENTITY" == "$BACKUP_RUNTIME_GCP_IDENTITY" ]] || die identity
  UPLOAD_AUTH_ARGS=(--impersonate-service-account "$BACKUP_GCP_IDENTITY")
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/leadflow-backup.XXXXXXXX")"
chmod 700 "$TMP"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NONCE="$(node -e "process.stdout.write(require('node:crypto').randomBytes(6).toString('hex'))")"
NAME="leadflow-${STAMP}-${NONCE}.tar.gcm"
COMPOSE=(docker compose -p "$BACKUP_COMPOSE_PROJECT" -f "$ROOT/compose.yaml" -f "$BACKUP_COMPOSE_OVERRIDE")

log generate START
N8N_ID="$("${COMPOSE[@]}" ps -q n8n)"
POSTGRES_ID="$("${COMPOSE[@]}" ps -q postgres)"
[[ -n "$N8N_ID" && "$N8N_ID" != *$'\n'* && -n "$POSTGRES_ID" && "$POSTGRES_ID" != *$'\n'* ]] || die compose_services
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' "$N8N_ID")" == "$BACKUP_COMPOSE_PROJECT|n8n" ]] || die n8n_container
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' "$POSTGRES_ID")" == "$BACKUP_COMPOSE_PROJECT|postgres" ]] || die postgres_container
N8N_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/node/.n8n"}}{{.Type}}|{{.Name}}{{end}}{{end}}' "$N8N_ID")"
[[ "$N8N_MOUNT" == volume\|* ]] || die n8n_volume
N8N_VOLUME="${N8N_MOUNT#volume|}"
[[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$N8N_VOLUME")" == "$BACKUP_COMPOSE_PROJECT" ]] || die n8n_volume
N8N_PAUSED=1
timeout 30 docker pause "$N8N_ID" >/dev/null
PAUSE_DEADLINE=$((SECONDS+BACKUP_PAUSE_TIMEOUT_SECONDS))
timeout "$((PAUSE_DEADLINE-SECONDS))" "${COMPOSE[@]}" exec -T postgres pg_dump \
  --format=custom --no-owner --no-privileges \
  --username "${POSTGRES_BOOTSTRAP_USER:?POSTGRES_BOOTSTRAP_USER is required}" \
  --dbname "${POSTGRES_DB:?POSTGRES_DB is required}" >"$TMP/postgres.dump"
[[ -s "$TMP/postgres.dump" ]] || die postgres_dump
mkdir "$TMP/n8n"
(( PAUSE_DEADLINE>SECONDS )) || die pause_timeout
timeout "$((PAUSE_DEADLINE-SECONDS))" docker cp "$N8N_ID:/home/node/.n8n/." "$TMP/n8n/"
timeout 30 docker unpause "$N8N_ID" >/dev/null
N8N_PAUSED=0
python3 - "$TMP/manifest.json" "$NAME" "$STAMP" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"format":"LF015-1","backup_id":sys.argv[2],"created_utc":sys.argv[3],"consistency":"n8n_paused_before_pg_dump_until_volume_copy"},separators=(",",":"))+"\n",encoding="utf-8")
PY
tar -C "$TMP" -cf "$TMP/payload.tar" manifest.json postgres.dump n8n
log generate PASS

log encrypt START
node "$ROOT/scripts/backup/backup_crypto.mjs" encrypt --key-file "$BACKUP_KEY_FILE" --input "$TMP/payload.tar" --output "$TMP/$NAME"
sha256sum "$TMP/$NAME" | awk '{print $1}' >"$TMP/$NAME.sha256"
rm -rf -- "$TMP/payload.tar" "$TMP/manifest.json" "$TMP/postgres.dump" "$TMP/n8n"
log encrypt PASS

log transfer START
DEST="${BACKUP_GCS_BUCKET%/}/$NAME"
python3 "$ROOT/scripts/backup/gcs_json_upload.py" --source "$TMP/$NAME" --destination "$DEST" --timeout "$GCS_UPLOAD_TIMEOUT_SECONDS" "${UPLOAD_AUTH_ARGS[@]}" >/dev/null
python3 "$ROOT/scripts/backup/gcs_json_upload.py" --source "$TMP/$NAME.sha256" --destination "$DEST.sha256" --timeout "$GCS_UPLOAD_TIMEOUT_SECONDS" "${UPLOAD_AUTH_ARGS[@]}" >/dev/null
log transfer PASS
rm -rf -- "$TMP" || die cleanup
TMP=""
printf 'backup artifact=%s status=PASS\n' "$NAME"
