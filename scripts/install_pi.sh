#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo scripts/install_pi.sh" >&2
  exit 1
fi

ROOT="${BC_ASSUMPTIONS_ROOT:-/opt/bc-assumptions-registry}"
SERVICE_USER="${BC_ASSUMPTIONS_USER:-bcassumptions}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

apt-get update
apt-get install -y git python3 python3-venv python3-pip util-linux poppler-utils

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
fi

if [[ "$SOURCE_DIR" != "$ROOT" ]]; then
  mkdir -p "$ROOT"
  cp -a "$SOURCE_DIR/." "$ROOT/"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$ROOT"

runuser -u "$SERVICE_USER" -- python3 -m venv "$ROOT/.venv"
runuser -u "$SERVICE_USER" -- "$ROOT/.venv/bin/python" -m pip install --upgrade pip
runuser -u "$SERVICE_USER" -- "$ROOT/.venv/bin/python" -m pip install -e "${ROOT}[regulatory]"
runuser -u "$SERVICE_USER" -- "$ROOT/.venv/bin/bc-assumptions" --root "$ROOT" init-db

cat > /etc/systemd/system/bc-assumptions.service <<EOF
[Unit]
Description=Update the BC assumptions evidence registry
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$ROOT
EnvironmentFile=-/etc/bc-assumptions.env
ExecStart=$ROOT/scripts/run_weekly.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=6
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=$ROOT

[Install]
WantedBy=multi-user.target
EOF
install -m 0644 "$ROOT/systemd/bc-assumptions.timer" /etc/systemd/system/bc-assumptions.timer
if [[ ! -f /etc/bc-assumptions.env ]]; then
  install -m 0600 "$ROOT/.env.example" /etc/bc-assumptions.env
fi
systemctl daemon-reload

echo "Edit /etc/bc-assumptions.env, configure Git credentials for $SERVICE_USER, then run:"
echo "  systemctl enable --now bc-assumptions.timer"
