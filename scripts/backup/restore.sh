#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; TMP=""; STATE_FILE=""; PHASE="preflight"; MUTATED=0
log(){ printf 'restore phase=%s status=%s\n' "$1" "$2"; }
write_state(){ [[ -n "$STATE_FILE" ]] || return 0; local next="$STATE_FILE.tmp"; printf 'phase=%s\nstatus=%s\ntraffic=DISABLED\nartifact=%s\n' "$PHASE" "$1" "${RESTORE_GCS_URI##*/}" >"$next" && chmod 600 "$next" && mv -f -- "$next" "$STATE_FILE"; }
cleanup(){ local status=$?; if [[ "$status" != 0 && "$MUTATED" == 1 ]]; then write_state RECOVERABLE_FAILURE || true; fi; [[ -z "$TMP" ]] || rm -rf -- "$TMP" || status=1; exit "$status"; }
die(){ log "${1:-preflight}" FAIL >&2; exit 1; }
trap cleanup EXIT; trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP

for command in python3 node docker sha256sum gcloud curl stat head tr cmp; do command -v "$command" >/dev/null || die preflight; done
[[ "${LEADFLOW_RESTORE_ISOLATED:-}" == true ]] || die isolation
[[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -z "${CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE:-}" && -z "${GCE_METADATA_HOST:-}" && -z "${GCE_METADATA_IP:-}" ]] || die credentials
[[ -n "${RESTORE_GCS_URI:-}" && "$RESTORE_GCS_URI" == gs://*.tar.gcm ]] || die source
[[ -n "${RESTORE_GCP_IDENTITY:-}" && -n "${BACKUP_GCP_IDENTITY:-}" && "$RESTORE_GCP_IDENTITY" != "$BACKUP_GCP_IDENTITY" ]] || die identity_separation
[[ -n "${DSR_EVIDENCE_WRITER_IDENTITY:-}" && -n "${DSR_EVIDENCE_ADMIN_IDENTITY:-}" && "$DSR_EVIDENCE_WRITER_IDENTITY" != "$DSR_EVIDENCE_ADMIN_IDENTITY" && "$DSR_EVIDENCE_WRITER_IDENTITY" != "$RESTORE_GCP_IDENTITY" && "$DSR_EVIDENCE_ADMIN_IDENTITY" != "$RESTORE_GCP_IDENTITY" && "$DSR_EVIDENCE_WRITER_IDENTITY" != "$BACKUP_GCP_IDENTITY" && "$DSR_EVIDENCE_ADMIN_IDENTITY" != "$BACKUP_GCP_IDENTITY" ]] || die identity_separation
[[ -n "${BACKUP_KEY_FILE:-}" && -r "$BACKUP_KEY_FILE" ]] || die key
[[ -n "${DSR_EVIDENCE_KEY_FILE:-}" && -r "$DSR_EVIDENCE_KEY_FILE" && "$DSR_EVIDENCE_KEY_FILE" != "$BACKUP_KEY_FILE" ]] || die dsr_evidence_key
cmp -s -- "$BACKUP_KEY_FILE" "$DSR_EVIDENCE_KEY_FILE" && die dsr_evidence_key
[[ -n "${DSR_EVIDENCE_URI:-}" && "$DSR_EVIDENCE_URI" == gs://*.dsr-bundle.gcm && "$DSR_EVIDENCE_URI" != "$RESTORE_GCS_URI" ]] || die dsr_evidence_source
[[ "${RESTORE_COMPOSE_OVERRIDE:-}" == /* && -f "$RESTORE_COMPOSE_OVERRIDE" ]] || die isolation
[[ -n "${SOURCE_COMPOSE_PROJECT:-}" && "${RESTORE_COMPOSE_PROJECT:?RESTORE_COMPOSE_PROJECT is required}" != "$SOURCE_COMPOSE_PROJECT" ]] || die isolation
[[ "${RESTORE_STATE_DIR:-}" == /* && -d "$RESTORE_STATE_DIR" && -w "$RESTORE_STATE_DIR" && "$(stat -c '%a' "$RESTORE_STATE_DIR")" == 700 ]] || die state_directory
for value in "${RESTORE_MAX_ENCRYPTED_BYTES:=53687091200}" "${RESTORE_MAX_EXTRACTED_BYTES:=107374182400}" "${RESTORE_MAX_MEMBER_BYTES:=53687091200}" "${RESTORE_MAX_ENTRIES:=100000}" "${DSR_EVIDENCE_MAX_BYTES:=1073741824}"; do [[ "$value" =~ ^[1-9][0-9]*$ && ${#value} -le 13 ]] || die limits; done
(( RESTORE_MAX_ENCRYPTED_BYTES<=1099511627776 && RESTORE_MAX_EXTRACTED_BYTES<=1099511627776 && RESTORE_MAX_MEMBER_BYTES<=1099511627776 && RESTORE_MAX_ENTRIES<=1000000 )) || die limits
METADATA_URL="http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
MANAGED_IDENTITY="$(curl --fail --silent --show-error --noproxy '*' --connect-timeout 2 --max-time 5 -H 'Metadata-Flavor: Google' "$METADATA_URL" 2>/dev/null)" || die identity
[[ "$MANAGED_IDENTITY" == "$RESTORE_GCP_IDENTITY" ]] || die identity

TMP="$(mktemp -d "${TMPDIR:-/tmp}/leadflow-restore.XXXXXXXX")"; chmod 700 "$TMP"; export CLOUDSDK_CONFIG="$TMP/gcloud"; mkdir -m 700 "$CLOUDSDK_CONFIG"
COMPOSE=(docker compose -p "$RESTORE_COMPOSE_PROJECT" -f "$ROOT/compose.yaml" -f "$RESTORE_COMPOSE_OVERRIDE")
"${COMPOSE[@]}" config --format json >"$TMP/compose.json" || die isolation
python3 - "$TMP/compose.json" <<'PY' || die isolation
import json,sys
c=json.load(open(sys.argv[1],encoding="utf-8")); s=c.get("services",{})
assert {"postgres","n8n"}.issubset(s) and not s["postgres"].get("ports") and not s["n8n"].get("ports")
PY
TARGET_N8N_ID="$("${COMPOSE[@]}" ps -aq n8n)"; TARGET_POSTGRES_ID="$("${COMPOSE[@]}" ps -q postgres)"
[[ -n "$TARGET_N8N_ID" && -n "$TARGET_POSTGRES_ID" ]] || die isolated_services
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$TARGET_N8N_ID")" == "$RESTORE_COMPOSE_PROJECT" ]] || die isolation
[[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$TARGET_POSTGRES_ID")" == "$RESTORE_COMPOSE_PROJECT" ]] || die isolation
TARGET_N8N_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/node/.n8n"}}{{.Type}}|{{.Name}}{{end}}{{end}}' "$TARGET_N8N_ID")"
[[ "$TARGET_N8N_MOUNT" == volume\|* ]] || die n8n_volume
TARGET_N8N_VOLUME="${TARGET_N8N_MOUNT#volume|}"
[[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$TARGET_N8N_VOLUME")" == "$RESTORE_COMPOSE_PROJECT" ]] || die n8n_volume
TARGET_POSTGRES_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Type}}|{{.Name}}{{end}}{{end}}' "$TARGET_POSTGRES_ID")"
[[ "$TARGET_POSTGRES_MOUNT" == volume\|* ]] || die postgres_volume
TARGET_POSTGRES_VOLUME="${TARGET_POSTGRES_MOUNT#volume|}"
[[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$TARGET_POSTGRES_VOLUME")" == "$RESTORE_COMPOSE_PROJECT" ]] || die postgres_volume
SOURCE_N8N_ID="$(docker ps -aq --filter "label=com.docker.compose.project=$SOURCE_COMPOSE_PROJECT" --filter 'label=com.docker.compose.service=n8n' | head -n 1)"
if [[ -n "$SOURCE_N8N_ID" ]]; then SOURCE_N8N_MOUNT="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/node/.n8n"}}{{.Name}}{{end}}{{end}}' "$SOURCE_N8N_ID")"; [[ "$SOURCE_N8N_MOUNT" != "$TARGET_N8N_VOLUME" ]] || die isolation; fi

ARTIFACT="$TMP/backup.tar.gcm"; PHASE="transfer"; log transfer START
REMOTE_SIZE="$(gcloud --quiet storage objects describe "$RESTORE_GCS_URI" --format='value(size)' 2>/dev/null)" || die source
[[ "$REMOTE_SIZE" =~ ^[0-9]+$ && ${#REMOTE_SIZE} -le 13 ]] && (( REMOTE_SIZE>0 && REMOTE_SIZE<=RESTORE_MAX_ENCRYPTED_BYTES )) || die encrypted_size
REMOTE_CHECKSUM_SIZE="$(gcloud --quiet storage objects describe "$RESTORE_GCS_URI.sha256" --format='value(size)' 2>/dev/null)" || die checksum
[[ "$REMOTE_CHECKSUM_SIZE" =~ ^[0-9]+$ ]] && (( REMOTE_CHECKSUM_SIZE>=64 && REMOTE_CHECKSUM_SIZE<=128 )) || die checksum
gcloud --quiet storage cp "$RESTORE_GCS_URI" "$ARTIFACT" >/dev/null
gcloud --quiet storage cp "$RESTORE_GCS_URI.sha256" "$ARTIFACT.sha256" >/dev/null
[[ "$(stat -c '%s' "$ARTIFACT")" == "$REMOTE_SIZE" ]] || die encrypted_size
[[ "$(stat -c '%s' "$ARTIFACT.sha256")" == "$REMOTE_CHECKSUM_SIZE" ]] || die checksum
EXPECTED_SHA256="$(tr -d '\r\n' <"$ARTIFACT.sha256")"; [[ "$EXPECTED_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || die checksum
(cd "$TMP" && printf '%s  %s\n' "$EXPECTED_SHA256" backup.tar.gcm | sha256sum --check --status) || die checksum
EVIDENCE_ARTIFACT="$TMP/evidence.dsr-bundle.gcm"
EVIDENCE_SIZE="$(gcloud --quiet storage objects describe "$DSR_EVIDENCE_URI" --format='value(size)' 2>/dev/null)" || die dsr_evidence_source
[[ "$EVIDENCE_SIZE" =~ ^[0-9]+$ && ${#EVIDENCE_SIZE} -le 13 ]] && (( EVIDENCE_SIZE>0 && EVIDENCE_SIZE<=DSR_EVIDENCE_MAX_BYTES )) || die dsr_evidence_size
EVIDENCE_CHECKSUM_SIZE="$(gcloud --quiet storage objects describe "$DSR_EVIDENCE_URI.sha256" --format='value(size)' 2>/dev/null)" || die dsr_evidence_checksum
[[ "$EVIDENCE_CHECKSUM_SIZE" =~ ^[0-9]+$ ]] && (( EVIDENCE_CHECKSUM_SIZE>=64 && EVIDENCE_CHECKSUM_SIZE<=128 )) || die dsr_evidence_checksum
gcloud --quiet storage cp "$DSR_EVIDENCE_URI" "$EVIDENCE_ARTIFACT" >/dev/null
gcloud --quiet storage cp "$DSR_EVIDENCE_URI.sha256" "$EVIDENCE_ARTIFACT.sha256" >/dev/null
[[ "$(stat -c '%s' "$EVIDENCE_ARTIFACT")" == "$EVIDENCE_SIZE" && "$(stat -c '%s' "$EVIDENCE_ARTIFACT.sha256")" == "$EVIDENCE_CHECKSUM_SIZE" ]] || die dsr_evidence_size
EVIDENCE_SHA256="$(tr -d '\r\n' <"$EVIDENCE_ARTIFACT.sha256")"; [[ "$EVIDENCE_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || die dsr_evidence_checksum
(cd "$TMP" && printf '%s  %s\n' "$EVIDENCE_SHA256" evidence.dsr-bundle.gcm | sha256sum --check --status) || die dsr_evidence_checksum
log transfer PASS

PHASE="decrypt_validate"; log decrypt_validate START
node "$ROOT/scripts/backup/backup_crypto.mjs" decrypt --key-file "$BACKUP_KEY_FILE" --input "$ARTIFACT" --output "$TMP/payload.tar" || die authentication
python3 "$ROOT/scripts/backup/validate_restore_archive.py" extract "$TMP/payload.tar" "$TMP/payload" "$RESTORE_MAX_ENTRIES" "$RESTORE_MAX_EXTRACTED_BYTES" "$RESTORE_MAX_MEMBER_BYTES" || die archive
[[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["backup_id"])' "$TMP/payload/manifest.json")" == "${RESTORE_GCS_URI##*/}" ]] || die archive_identity
"${COMPOSE[@]}" exec -T postgres pg_restore --list <"$TMP/payload/postgres.dump" >/dev/null || die postgres_dump
DSR_BUNDLE_RESULT="$(python3 "$ROOT/scripts/backup/dsr_restore_evidence.py" validate-bundle --key-file "$DSR_EVIDENCE_KEY_FILE" --input "$EVIDENCE_ARTIFACT" --output "$TMP/dsr-bundle.json" --backup-manifest "$TMP/payload/manifest.json")" || die dsr_evidence
DSR_EVENT_COUNT="$(python3 -c 'import json,sys;print(json.loads(sys.argv[1])["event_count"])' "$DSR_BUNDLE_RESULT")"; [[ "$DSR_EVENT_COUNT" =~ ^[0-9]+$ ]] || die dsr_evidence
python3 "$ROOT/scripts/backup/dsr_restore_evidence.py" emit-sql --input "$TMP/dsr-bundle.json" --output "$TMP/dsr-replay.sql" >/dev/null || die dsr_evidence
log decrypt_validate PASS

STATE_FILE="$RESTORE_STATE_DIR/restore-${RESTORE_GCS_URI##*/}.state"; [[ ! -e "$STATE_FILE" ]] || die existing_restore_state
(set -o noclobber; : >"$STATE_FILE") || die state_file; chmod 600 "$STATE_FILE"
PHASE="prepared"; write_state PREPARED || die state_file
MUTATED=1; PHASE="postgres_restore"; write_state IN_PROGRESS
"${COMPOSE[@]}" stop n8n >/dev/null
"${COMPOSE[@]}" exec -T postgres pg_restore --exit-on-error --clean --if-exists --no-owner --no-privileges --username "${POSTGRES_BOOTSTRAP_USER:?POSTGRES_BOOTSTRAP_USER is required}" --dbname "${POSTGRES_DB:?POSTGRES_DB is required}" <"$TMP/payload/postgres.dump"

PHASE="n8n_restore"; write_state IN_PROGRESS
TARGET_N8N_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$TARGET_N8N_ID")"; [[ -n "$TARGET_N8N_IMAGE" ]] || die n8n_image
docker run --rm --network none --read-only -v "$TARGET_N8N_VOLUME:/target" -v "$TMP/payload/n8n:/source:ro" --entrypoint sh "$TARGET_N8N_IMAGE" -c 'find /target -mindepth 1 -delete && cp -R /source/. /target/' >/dev/null

PHASE="dsr_replay"; write_state IN_PROGRESS
DSR_RESULT="$("${COMPOSE[@]}" exec -T postgres psql -X -q -v ON_ERROR_STOP=1 --username "$POSTGRES_BOOTSTRAP_USER" --dbname "$POSTGRES_DB" -At <"$TMP/dsr-replay.sql")" || die dsr_replay
[[ "$DSR_RESULT" == "$DSR_EVENT_COUNT|$DSR_EVENT_COUNT|$DSR_EVENT_COUNT" ]] || die dsr_post_verification
PHASE="complete"; write_state PASS
rm -rf -- "$TMP" || die cleanup; TMP=""; printf 'restore status=PASS traffic=DISABLED state=%s\n' "$STATE_FILE"
