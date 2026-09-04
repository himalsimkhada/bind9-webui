#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "==> Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq bind9 bind9utils bind9-dnsutils python3-venv

echo "==> Ensuring rndc key exists and has correct permissions..."
if [ ! -f /etc/bind/rndc.key ]; then
    sudo rndc-confgen -a
fi
sudo chmod 640 /etc/bind/rndc.key
sudo chown root:bind /etc/bind/rndc.key

echo "==> Setting up Python venv..."
python3 -m venv venv
./venv/bin/pip install -q -r requirements.txt

echo "==> Starting named..."
sudo systemctl start named 2>/dev/null || sudo named
sleep 1

if ! sudo rndc status >/dev/null 2>&1; then
    echo "WARNING: named may not be running correctly. Check: sudo rndc status"
fi

echo "==> Installing systemd service..."
sudo cp bind9-webui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bind9-webui
sudo systemctl restart bind9-webui

echo ""
echo "==> Done! Web UI running at http://localhost:5000"
echo "    sudo systemctl status bind9-webui"
