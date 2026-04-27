#!/usr/bin/env bash
set -euo pipefail

# Ella Telegram Deploy — install systemd services
# Must be run with sudo: sudo bash install.sh

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: This script must be run as root (sudo)."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES=("ella-telegram.service" "comfyui.service" "llama-server.service" "prompt-guard.service")

echo "=== Installing systemd services ==="

for svc in "${SERVICES[@]}"; do
  echo "  Copying $svc -> /etc/systemd/system/$svc"
  cp "$SCRIPT_DIR/$svc" /etc/systemd/system/
done

echo ""
echo "=== Reloading systemd daemon ==="
systemctl daemon-reload

echo ""
echo "=== Enabling services ==="
for svc in "${SERVICES[@]}"; do
  systemctl enable "$svc"
  echo "  Enabled: $svc"
done

echo ""
echo "=== Done ==="
echo ""
echo "Services installed and enabled. They will start automatically on boot."
echo ""
echo "To start all services now:"
echo "  sudo systemctl start llama-server comfyui prompt-guard ella-telegram"
echo ""
echo "To check status:"
echo "  sudo systemctl status ella-telegram"
echo "  sudo systemctl status comfyui"
echo "  sudo systemctl status llama-server"
echo "  sudo systemctl status prompt-guard"
echo ""
echo "To view logs:"
echo "  journalctl -u ella-telegram -f"
echo "  journalctl -u comfyui -f"
echo "  journalctl -u llama-server -f"
echo "  journalctl -u prompt-guard -f"
