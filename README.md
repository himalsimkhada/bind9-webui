# bind9-webui

A lightweight web interface for managing BIND9 (named) DNS server. Runs on top of your existing BIND9 installation — no modifications to your DNS setup required.

## Features

- **Dashboard** — structured server status with stat boxes, rndc controls (reload, flush, stats, querylog)
- **Zone Management** — create/delete zones, add/remove records (A, AAAA, MX, CNAME, NS, TXT, SRV, PTR), edit raw zone files directly
- **Zone Source Control** — one-click move zones between `named.conf.local` and `named.conf.default-zones`, with protected flag for built-in system zones and filesystem path display
- **Host Mapper** — paste or upload `IP host1 host2 ...` lines to bulk-create A records in existing zones (with duplicate and missing-zone reporting)
- **Configuration** — edit all conf files (`named.conf`, `named.conf.options`, `named.conf.local`, `named.conf.default-zones`) with full comment preservation
- **Backup / Restore** — one-click download of all config + zone files (+ rndc key) as a gzipped tarball, and validated restore (`named-checkconf`/`named-checkzone`; config gate is hard, zone issues reported as warnings)
- **DNS Lookup (Dig)** — run `dig` queries from the UI against the managed BIND
- **Logs** — built-in log viewer with line count control and text filtering
- **Validation** — zone and config checking via `named-checkconf` / `named-checkzone`
- **Access Protection** — single shared password (`WEBUI_PASSWORD`), "remember me" 30-minute auto-logout session, log out button, and brute-force lockout (5 failed logins → 15 min block)
- **Dark/Light Mode** — toggle theme, persisted in browser
- **Minimal footprint** — Flask + vanilla HTML/CSS/JS, ~32 MB RAM

## Requirements

- Linux with BIND9 installed (`apt install bind9 bind9-dnsutils`)
- Python 3.10+
- `sudo` access (for rndc and named config files)
- Docker is optional — only required for the containerized deployment.

## Deployment Options

The web UI is deliberately flexible and can run against **either** a bare-metal
BIND (the default) **or** an Ubuntu BIND container — without code changes. It
talks to `named` through whichever transport you configure:

- **Local (bare-metal):** `rndc` over the local UNIX control socket, reading/writing `/etc/bind/`.
- **Remote (container or host over network):** `rndc` over TCP port 953 with a shared `rndc.key`.

### Option 1 — Bare-metal (default)

```bash
git clone https://github.com/himalsimkhada/bind9-webui.git
cd bind9-webui
sudo bash install.sh
```
Web UI at `http://localhost:5000`.

### Option 2 — Full Docker stack (BIND + web UI, two containers)

```bash
docker compose -f docker-compose-w-bind9.yml up -d --build
```
- `bind9` — the official `ubuntu/bind9` container (port 53 UDP/TCP, plus TCP 953 for rndc).
- `webui` — this project's image (port 5000).

Both share `./docker/bind/` config (`named.conf`, `rndc.key`, …) and two named
volumes (`bind-zones` for zone data files, `bind-logs` for `named.log`). The
web-UI container drives BIND over `rndc -s bind9 -p 953`.

> **rndc key:** a pre-generated `rndc.key` is committed under `docker/bind/`.
> For production, regenerate it before deployment:
> ```bash
> rndc-confgen -a -c docker/bind/rndc.key && chmod 644 docker/bind/rndc.key
> ```

### Option 3 — web-UI container controlling a host / remote BIND

Run only the web-UI image and have it manage BIND that already runs elsewhere
(the bare-metal host, or another machine). Use `docker-compose.yml` — it mounts
the host's `/etc/bind` into the container and manages the host's `named` over
the rndc TCP channel:

```bash
cp .env.example .env    # RNDC_HOST defaults to host.docker.internal
docker compose up -d --build
```

The compose file adds `extra_hosts: host.docker.internal → host-gateway`, so the
container reaches the Docker host automatically (no need to hardcode a gateway IP).
If your Docker doesn't support `host-gateway`, set `RNDC_HOST` in `.env` to the
host's LAN IP or the compose network gateway.

> **Requirement:** a container cannot reach the host's local rndc UNIX control
> socket, so the target `named` must listen on TCP 953. If your `named.conf`
> does not already expose it, add a **restricted** block (never `allow { any; }`)
> ```
> controls { inet 0.0.0.0 port 953 allow { 127.0.0.1; ::1; 172.16.0.0/12; } keys { "rndc-key"; }; };
> ```
> then restart named, e.g. `sudo systemctl restart named`. Also ensure the
> mounted `/etc/bind` contains the matching `rndc.key`. The `172.16.0.0/12`
> covers Docker bridge/compose subnetworks (the range Docker assigns); tighten
> it to your exact subnet if you prefer.

For the **Logs** tab, host BIND should also write a log file. Add to the host's
`named.conf.options` (so the mounted `/var/log/bind` has content to tail):

```
logging {
    channel bind_webui_file { file "/var/log/bind/named.log" versions 3 size 5m; severity info; };
    category default { bind_webui_file; };
    category queries { bind_webui_file; };
};
```

All web-UI container settings are configured via the `.env` file (see
`.env.example`): `RNDC_HOST`, `RNDC_PORT`, `WEBUI_PORT`, `LOG_FILE`.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BIND_CONF_DIR` | `/etc/bind` | Directory holding `named.conf*.local/.default-zones/options` |
| `ZONE_DIR` | `$BIND_CONF_DIR` | Where zone data files (`db.<zone>`) are written |
| `ZONE_OWNER` | *(empty)* | `user:group` to chown new zone files to (e.g. `bind:bind` in Docker) |
| `RNDC_HOST` | *(empty → local socket)* | Hostname/IP of a remote `named` over TCP (e.g. `bind9`) |
| `RNDC_PORT` | `953` | rndc TCP port when `RNDC_HOST` is set |
| `RNDC_KEY` | `$BIND_CONF_DIR/rndc.key` | rndc key file path |
| `LOG_FILE` | *(auto)* | Path to a BIND log file to tail (containers) instead of `journalctl` |
| `WEBUI_PASSWORD` | *(empty = auth off)* | Single shared password required to use the UI |
| `SECRET_KEY` | *(dev default)* | Secret used to sign the session cookie; set a random value |

> **Access protection:** Set `WEBUI_PASSWORD` to require a password. The login
> screen has a *Remember me* checkbox that persists the session for **30 minutes**
> then auto-logs-out; without it the session ends when the browser closes. A
> **Log out** button appears in the nav bar. If `WEBUI_PASSWORD` is empty,
> authentication is disabled entirely.

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

# Run (password-protected; omit WEBUI_PASSWORD to disable auth)
WEBUI_PASSWORD='your-password' SECRET_KEY='a-long-random-string' ./venv/bin/python3 app.py
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
├── static/style.css        # Dark/Light theme CSS
├── static/app.js           # Vanilla JS (no build step)
├── requirements.txt        # flask
├── Dockerfile              # Container image for the web UI
├── docker-compose.yml      # Web-UI only (manages host/remote BIND over TCP rndc)
├── docker-compose-w-bind9.yml  # Full stack: BIND9 container + web UI
├── .env.example            # Sample env for docker-compose.yml (web-UI only)
├── docker/bind/            # Config/rndc.key shared with the BIND container
│   ├── named.conf
│   ├── named.conf.options
│   ├── named.conf.local
│   ├── named.conf.default-zones
│   └── rndc.key
├── install.sh              # One-shot bare-metal setup script
└── bind9-webui.service     # Systemd unit file
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | BIND9 server status (raw) |
| GET | `/api/status/structured` | Server status (parsed key-value) |
| GET | `/api/zones` | List all zones |
| GET | `/api/zone/<name>` | Zone detail + records + path + source |
| POST | `/api/zone` | Create zone |
| DELETE | `/api/zone/<name>` | Delete zone |
| PUT | `/api/zone/<name>/file` | Update raw zone file |
| POST | `/api/zone/<name>/source` | Move zone between config files |
| POST | `/api/map-hosts` | Bulk-create A records from `IP host...` lines |
| POST | `/api/zone/<name>/record` | Add record |
| DELETE | `/api/zone/<name>/record/<idx>` | Remove record |
| GET | `/api/config/files` | List editable config files |
| GET | `/api/config/file/<name>` | Read config file |
| PUT | `/api/config/file/<name>` | Update config file |
| GET | `/api/config/check` | Run named-checkconf |
| GET | `/api/zone/<name>/check` | Run named-checkzone |
| GET | `/api/logs` | Query named logs |
| POST | `/api/control/reload` | rndc reload |
| POST | `/api/control/flush` | rndc flush |

## How It Works

The web UI communicates with BIND9 through:

- **`rndc`** — for server control (reload, flush, stats, querylog); over the local UNIX socket on bare-metal, or over TCP 953 toward a container/remote BIND
- **`/etc/bind/` config files** — read/write `named.conf.local`, zone files
- **`named-checkconf` / `named-checkzone`** — for validation
- **`journalctl` / a log file** — for log viewing (containers tail `LOG_FILE`)

The transport is chosen automatically from the environment: running as the
systemd service it uses the local socket; in a container it uses `RNDC_HOST`
over TCP. No database required. Just reads and writes the same files (or talks
to the same control channel) that BIND9 uses.

## License

MIT
