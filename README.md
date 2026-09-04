# bind9-webui

A lightweight web interface for managing BIND9 (named) DNS server. Runs on top of your existing BIND9 installation — no modifications to your DNS setup required.

## Features

- **Dashboard** — server status, rndc controls (reload, flush, stats, querylog)
- **Zone Management** — create/delete zones, add/remove records (A, AAAA, MX, CNAME, NS, TXT, SRV, PTR)
- **Config Editor** — edit `named.conf.options` directly in the browser
- **Validation** — zone and config checking via `named-checkconf` / `named-checkzone`
- **Minimal footprint** — Flask + vanilla HTML/CSS/JS, ~32 MB RAM

## Requirements

- Linux with BIND9 installed (`apt install bind9 bind9-dnsutils`)
- Python 3.10+
- `sudo` access (for rndc and named config files)

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/bind9-webui.git
cd bind9-webui
sudo bash install.sh
```

Web UI will be available at `http://localhost:5000`.

## Manual Setup

```bash
# Install dependencies
sudo apt install bind9 bind9utils bind9-dnsutils python3-venv

# Fix rndc key permissions (if needed)
sudo rndc-confgen -a
sudo chmod 640 /etc/bind/rndc.key
sudo chown root:bind /etc/bind/rndc.key

# Ensure named is running
sudo systemctl start named

# Set up Python venv
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Run
./venv/bin/python3 app.py
```

## Systemd Service

To run as a system service that starts on boot:

```bash
sudo cp bind9-webui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bind9-webui
```

## Project Structure

```
bind9-web-ui/
├── app.py                  # Flask app — API routes + serves UI
├── bind_manager.py         # rndc commands + zone/config file parsing
├── templates/index.html    # Single-page dashboard
├── static/style.css        # Dark minimal CSS
├── static/app.js           # Vanilla JS (no build step)
├── requirements.txt        # flask
├── install.sh              # One-shot setup script
└── bind9-webui.service     # Systemd unit file
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | BIND9 server status |
| GET | `/api/zones` | List all zones |
| GET | `/api/zone/<name>` | Zone detail + records |
| POST | `/api/zone` | Create zone |
| DELETE | `/api/zone/<name>` | Delete zone |
| POST | `/api/zone/<name>/record` | Add record |
| DELETE | `/api/zone/<name>/record/<idx>` | Remove record |
| GET | `/api/config/options` | Get named.conf.options |
| PUT | `/api/config/options` | Update named.conf.options |
| GET | `/api/config/check` | Run named-checkconf |
| GET | `/api/zone/<name>/check` | Run named-checkzone |
| POST | `/api/control/reload` | rndc reload |
| POST | `/api/control/flush` | rndc flush |

## How It Works

The web UI communicates with BIND9 through:

- **`rndc`** — for server control (reload, flush, stats, querylog)
- **`/etc/bind/` config files** — read/write `named.conf.local`, zone files
- **`named-checkconf` / `named-checkzone`** — for validation

No database required. No additional services. Just reads and writes the same files your BIND9 installation uses.

## License

MIT
