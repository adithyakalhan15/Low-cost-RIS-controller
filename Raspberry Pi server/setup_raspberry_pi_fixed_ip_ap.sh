#!/usr/bin/env bash
set -euo pipefail

SSID="RIS_NET"
PASS="risdemo123"
AP_IP="192.168.50.1/24"
CON_NAME="RIS_AP"
IFACE="wlan0"

echo "[1/5] Installing basic packages..."
sudo apt update
sudo apt install -y python3-venv python3-pip network-manager

echo "[2/5] Creating/refreshing NetworkManager AP connection..."
sudo nmcli con delete "$CON_NAME" >/dev/null 2>&1 || true
sudo nmcli con add type wifi ifname "$IFACE" con-name "$CON_NAME" autoconnect yes ssid "$SSID"
sudo nmcli con modify "$CON_NAME" 802-11-wireless.mode ap 802-11-wireless.band bg
sudo nmcli con modify "$CON_NAME" ipv4.method shared ipv4.addresses "$AP_IP"
sudo nmcli con modify "$CON_NAME" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASS"

echo "[3/5] Starting AP..."
sudo nmcli con up "$CON_NAME"

echo "[4/5] Creating Python virtual environment..."
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[5/5] Done. Raspberry Pi AP should be: 192.168.50.1"
echo "Run controller with: ./run_controller.sh"
