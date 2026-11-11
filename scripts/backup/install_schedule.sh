#!/usr/bin/env bash
set -Eeuo pipefail
for command in stat install systemctl id getent runuser; do command -v "$command" >/dev/null || { echo "missing dependency: $command" >&2; exit 2; }; done
[[ $# == 1 && -f "$1" ]] || { echo 'usage: install_schedule.sh /absolute/path/to/environment-file' >&2; exit 2; }
[[ "$1" == /* ]] || { echo 'environment file path must be absolute' >&2; exit 2; }
[[ "$(stat -c '%a' "$1")" =~ ^[46]00$ ]] || { echo 'environment file must be owner-readable and not group/world readable' >&2; exit 2; }
[[ "${BACKUP_SERVICE_USER:-}" =~ ^[a-z_][a-z0-9_-]*$ && "${BACKUP_SERVICE_GROUP:-}" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo 'BACKUP_SERVICE_USER and BACKUP_SERVICE_GROUP are required' >&2; exit 2; }
id -u "$BACKUP_SERVICE_USER" >/dev/null 2>&1 && getent group "$BACKUP_SERVICE_GROUP" >/dev/null || { echo 'backup service identity does not exist' >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
for file in "$ROOT/scripts/backup/backup.sh" "$ROOT/scripts/backup/backup_crypto.mjs" "$ROOT/scripts/validation/validate_backup_policy.py"; do runuser -u "$BACKUP_SERVICE_USER" -- test -r "$file" || { echo 'backup runtime file is not readable by service user' >&2; exit 2; }; done
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
install -m 0644 /dev/stdin "$UNIT_DIR/leadflow-backup.service" <<EOF
[Unit]
Description=LeadFlow encrypted backup
[Service]
Type=oneshot
User=$BACKUP_SERVICE_USER
Group=$BACKUP_SERVICE_GROUP
EnvironmentFile=$1
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/usr/bin/env bash $ROOT/scripts/backup/backup.sh
PrivateTmp=true
NoNewPrivileges=true
UMask=0077
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
EOF
install -m 0644 /dev/stdin "$UNIT_DIR/leadflow-backup.timer" <<'EOF'
[Unit]
Description=Run LeadFlow backup every 24 hours
[Timer]
OnBootSec=15min
OnUnitActiveSec=24h
Persistent=true
Unit=leadflow-backup.service
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
echo 'schedule installed but not enabled'
