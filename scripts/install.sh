#!/usr/bin/env bash
# Automates the manual "Installation & setup" steps from README.md and
# registers the app as a systemd service so it starts automatically on
# every boot and restarts if it crashes.
#
# Intended for a production Raspberry Pi that's actually running the
# watering system. For local development, follow the manual steps in
# README.md instead — this script installs system packages (via apt/sudo)
# and a systemd unit, which you don't want on a dev machine.
#
# Usage: bash scripts/install.sh
# Safe to re-run (e.g. after pulling new dependencies).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/app"
VENV_DIR="$APP_DIR/venv"
SERVICE_USER="$(whoami)"
SERVICE_NAME="smart-watering"

echo "==> Installing into $APP_DIR as user $SERVICE_USER"
cd "$APP_DIR"

# 1. Create the virtual environment
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 2. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 2.5 Raspberry Pi GPIO backend for gpiozero. Without this, gpiozero falls
# back to its experimental NativeFactory, which can claim/release a pin
# correctly but won't reliably drive it on demand (see the Wiring section
# in README.md for the symptom and why this fixes it).
sudo apt update
sudo apt install -y swig liblgpio-dev
pip install lgpio

# 3. Create the database and apply migrations
alembic upgrade head

# 4. Configure the valve pin/polarity, if not already done
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "==> Created app/.env from .env.example."
    echo "    Edit VALVE_GPIO_PIN / VALVE_ACTIVE_HIGH to match your wiring"
    echo "    before relying on the valve — see README.md's Wiring section."
fi

deactivate

# 5. Register and start the systemd service so the app survives reboots
echo "==> Installing systemd service '$SERVICE_NAME'"
sudo tee "/etc/systemd/system/$SERVICE_NAME.service" > /dev/null <<EOF
[Unit]
Description=Smart Watering System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/fastapi run main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo "==> Done. The app now starts automatically on every boot."
echo "    Check status:  sudo systemctl status $SERVICE_NAME"
echo "    View logs:     sudo journalctl -u $SERVICE_NAME -f"
echo "    Restart:       sudo systemctl restart $SERVICE_NAME"
