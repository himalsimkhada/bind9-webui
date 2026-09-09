<div align="center">

```
 /$$       /$$                 /$$  /$$$$$$                                  /$$                 /$$
| $$      |__/                | $$ /$$__  $$                                | $$                |__/
| $$$$$$$  /$$ /$$$$$$$   /$$$$$$$| $$  \ $$         /$$  /$$  /$$  /$$$$$$ | $$$$$$$  /$$   /$$ /$$
| $$__  $$| $$| $$__  $$ /$$__  $$|  $$$$$$$ /$$$$$$| $$ | $$ | $$ /$$__  $$| $$__  $$| $$  | $$| $$
| $$  \ $$| $$| $$  \ $$| $$  | $$ \____  $$|______/| $$ | $$ | $$| $$$$$$$$| $$  \ $$| $$  | $$| $$
| $$  | $$| $$| $$  | $$| $$  | $$ /$$  \ $$        | $$ | $$ | $$| $$_____/| $$  | $$| $$  | $$| $$
| $$$$$$$/| $$| $$  | $$|  $$$$$$$|  $$$$$$/        |  $$$$$/$$$$/|  $$$$$$$| $$$$$$$/|  $$$$$$/| $$
|_______/ |__/|__/  |__/ \_______/ \______/          \_____/\___/  \_______/|_______/  \______/ |__/
                                                                                                    
                                                                                                    
                                                                                                    
```

### The API backend that powers your BIND9 management dashboard

**A lightweight, dependency-free API service** that manages BIND9 (`named`) exactly like you do from the shell — zero rebuilding, zero reconfiguration, no database, ~32 MB RAM.

<!-- badges (static, no network lookups) -->
![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![BIND9](https://img.shields.io/badge/BIND9-9.10+-9A3324?logo=processingfoundation&logoColor=white)
![Stack](https://img.shields.io/badge/Flask-Docker-Vanilla%20API-green)
![Docker](https://img.shields.io/badge/Docker-24273D?logo=docker&logoColor=white)
![API](https://img.shields.io/badge/API-only-yellow)
![maintained](https://img.shields.io/badge/maintained-yes-2ea44f)
![PRs](https://img.shields.io/badge/PRs-welcome-2ea44f)

This repo is the **API backend**. The user interface lives in the companion
facade [himalsimkhada/webui](https://github.com/himalsimkhada/webui), which
logs in to this service and proxies its dashboard to the browser. Point the
facade at `bind=http://…:5000` and you get the full BIND9 admin UI.

</div>

---

## Install — one line

Copy-paste this. No cloning, no setup — the installer keeps the project in the
directory you run it from, fetches the compose file (saved as
`docker-compose.yml`) for the deployment you pick, then deploys:

```bash
curl -fsSL https://raw.githubusercontent.com/himalsimkhada/bind9-webui/main/install.sh | bash
```

> Not ready yet? `./install.sh --check` does a safe dry run and reports what the
> installer would detect on your machine without changing anything.

---

## Table of Contents

- [Why a BIND9 backend?](#why-a-bind9-backend)
- [Features](#features)
- [Quick start](#quick-start)
- [Requirements](#requirements)
- [Deployment options](#deployment-options)
  - [1. Full Docker stack](#option-1--full-docker-stack)
  - [2. Host BIND + Docker](#option-2--host-bind--docker)
- [Configuration](#configuration)
- [Security notes](#security-notes)
- [API reference](#api-reference)
- [Development](#development)
- [Project structure](#project-structure)
- [How it works](#how-it-works)
- [License](#license)

---

## Why a BIND9 backend?

BIND9 administration normally means SSH-ing in, remembering `rndc` incantations,
and hand-editing zone files that are easy to get wrong. This project turns those
operations into a **clean HTTP API** — while **touching nothing** about how
BIND runs underneath.

It deals only with the same config files and the same control channel real
admins use (`rndc`, `named-checkconf`, `named-checkzone`). The API serves JSON,
auth-protected with the same shared password the facade uses. Your DNS setup
stays yours; the dashboard just makes it pleasant.

---

## Features

| | |
|---|---|
| **Server status** | `/api/status` raw `rndc status` plus `/api/status/structured` (parsed key-values: version, zones, workers, boot time, query logging). |
| **Zone management** | List, create, detail (records + SOA + raw file), edit records, raw zone-file save, delete — full CRUD API. |
| **Add-zone validation** | `/api/zone/preview` builds a zone file client-side (Simple wizard) and `/api/zone` validates raw bodies with `named-checkzone` before writing. |
| **Record operations** | Add single records, delete by index, or bulk-update a zone's records. |
| **Host Mapper** | `/api/map-hosts` turns `IP host1 host2 …` lines into A records across matching zones, with duplicate / missing-zone reporting. |
| **Source control** | Move zones (`/api/zone/<name>/source`) between `named.conf.local` and `named.conf.default-zones`; the API respects the protected flag on built-in system zones. |
| **Config editor** | Read/write `named.conf`, `named.conf.options`, `named.conf.local`, `named.conf.default-zones` with full comment preservation. |
| **Validation** | `named-checkconf` / `named-checkzone` on demand, before and after edits. |
| **Backup & restore** | Gzipped tarball of all config + zones (+ rndc key); validated restore with a hard config gate and zone issues downgraded to warnings. |
| **DNS lookup (Dig)** | `dig` from the API against the managed BIND. |
| **Log viewer** | BIND log tail with line-count control and text filtering. |
| **rndc controls** | `reload`, `flush`, `stats`, `querylog` toggle. |
| **Probes & metrics** | `/healthz`, `/readyz` for the facade's health checks and `/metrics` (Prometheus text) for the dashboard metrics tiles. |
| **Access protection** | Shared password (`WEBUI_PASSWORD`) with session cookie, *remember me* (30 min auto-logout), and brute-force lockout (5 failures → 15 min block). |
| **Feather-light** | Flask + stdlib tools. No build step, no Node.js, no database — ~32 MB RAM. |

---

## Quick start

Install in one command — the installer writes the project into the directory you
run it from and saves the compose file (of the mode you pick) as
`docker-compose.yml`, no repo clone:

```bash
curl -fsSL https://raw.githubusercontent.com/himalsimkhada/bind9-webui/main/install.sh | bash
```

Headless/scripted runs (no terminal) can skip the prompts with env vars —
`BIND9_MODE` (1 or 2), `TARGET_DIR` (default: current dir), `WEBUI_PASSWORD`:

```bash
BIND9_MODE=1 WEBUI_PASSWORD='your-password' \
  curl -fsSL https://raw.githubusercontent.com/himalsimkhada/bind9-webui/main/install.sh | bash
```

Or clone and run directly:

```bash
git clone https://github.com/himalsimkhada/bind9-webui.git
cd bind9-webui
./install.sh
```

You'll be asked which deployment you want:

```
  1) Full Docker stack   - BIND9 and the API both in containers
  2) Host BIND + Docker  - API container managing BIND on this machine
```

The API ends up on **port 5000**. To get the dashboard, point the
[webui facade](https://github.com/himalsimkhada/webui) at
`bind=http://<this-host>:5000` and open the facade (default `http://localhost:8080`).

> **Dry run first:** `./install.sh --check` reports what the installer detects
> on your machine (distro, BIND config dir, log dir, rndc key, installed
> dependencies) without changing a thing.
>
> **Dashboard included:** the installer detects when the companion webui admin
> facade ([himalsimkhada/webui](https://github.com/himalsimkhada/webui)) is not
> running and offers to install it for you — the portal hosts the dashboard UI,
> while this service stays API-only.

---

## Requirements

- Linux with BIND9 installed (`apt install bind9 bind9-dnsutils`)
- `sudo` access (for `rndc` and named config files)
- Docker is **optional** — needed only for the containerized deployments

Supported distros: Debian/Ubuntu (apt), RHEL/Fedora (dnf), Arch (pacman).

---

## Deployment options

The API runs against **either** a bare-metal BIND or a BIND container,
**without code changes** — it talks to `named` through whichever transport you configure:

- **Local (bare-metal):** `rndc` over the local UNIX control socket, reading/writing `/etc/bind/`.
- **Remote (container or host over network):** `rndc` over TCP 953 with a shared `rndc.key`.

| Option | What runs where | When to pick it |
|---|---|---|
| **1. Full Docker stack** | BIND9 + API, two containers | You want zero DNS tooling on the host |
| **2. Host BIND + Docker** | API in a container, BIND on the host | You keep your existing BIND, backend stays containerized |

### Option 1 — Full Docker stack

Two containers, one command: the official `internetsystemsconsortium/bind9` image and this project's API (port 5000). They share `./docker/bind/` config and two named volumes (`bind-zones`, `bind-logs`); the API drives BIND over `rndc -s bind9 -p 953`.

> **Ports:** DNS is published on host **127.0.0.1:5353** (TCP/UDP, mapped to the
> container's 53) and rndc on **127.0.0.1:9353** — non-default ports so the
> stack never collides with systemd-resolved (53) or a host `named` (953). To
> serve DNS at the standard port, edit the `ports:` block in
> `docker-compose.yml` and map `53:53/udp` + `53:53/tcp`. To publish on
> the LAN, use your machine's IP instead of `127.0.0.1`.

```bash
docker compose -f docker-compose.yml up -d
```

> **Production note:** a pre-generated `rndc.key` ships under `docker/bind/`.
> Regenerate it before exposing anything:
> ```bash
> rndc-confgen -a -c docker/bind/rndc.key && chmod 644 docker/bind/rndc.key
> ```

### Option 2 — Host BIND + Docker
Run only the API image and point it at BIND that already runs on the host (or elsewhere). The compose file mounts the host's `/etc/bind` into the container and manages `named` over the rndc TCP channel:

```bash
./install.sh     # choose 2) Host BIND + Docker
```

The installer detects your OS and BIND config dir (`/etc/bind` on Debian/Ubuntu, `/etc/named` on RHEL/Arch), verifies BIND, adds a **restricted** rndc `controls` block, adds a file logging channel, writes `.env`, then `docker compose up -d`. Manually:

```bash
cp .env.example .env    # RNDC_HOST defaults to host.docker.internal
docker compose up -d
```

The compose file adds `extra_hosts: host.docker.internal → host-gateway`, so the container finds the Docker host automatically. If your Docker doesn't support `host-gateway`, set `RNDC_HOST` in `.env` to the host's LAN IP or the compose gateway.

> **TCP 953 is required** — a container can't reach the host's local rndc UNIX
> socket. If your `named.conf` doesn't expose it, add a **restricted** block
> (never `allow { any; }`):
> ```
> controls { inet 0.0.0.0 port 953 allow { 127.0.0.1; ::1; 172.16.0.0/12; } keys { "rndc-key"; }; };
> ```
> then `sudo systemctl restart named`. Also make sure the mounted `/etc/bind`
> contains the matching `rndc.key`. The `172.16.0.0/12` covers Docker's default
> bridge/compose subnetworks — tighten it if you prefer.

For the **Logs** tab to have content, have the host BIND write a file so the mounted `/var/log/bind` has a log to tail (`named.conf.options`):

```
logging {
    channel bind_webui_file { file "/var/log/bind/named.log" versions 3 size 5m; severity info; };
    category default { bind_webui_file; };
    category queries { bind_webui_file; };
};
```

---

## Configuration

All container settings live in `.env` (see `.env.example`); bare-metal uses environment variables or the systemd `EnvironmentFile`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `BIND_CONF_DIR` | `/etc/bind` | Directory with `named.conf*.local/.default-zones/options` |
| `ZONE_DIR` | `$BIND_CONF_DIR` | Where zone data files (`db.<zone>`) are written |
| `ZONE_OWNER` | *(empty)* | `user:group` to chown new zone files to (e.g. `bind:bind` in Docker) |
| `RNDC_HOST` | *(empty → local socket)* | Hostname/IP of a remote `named` over TCP (e.g. `bind9`) |
| `RNDC_PORT` | `953` | rndc TCP port when `RNDC_HOST` is set |
| `RNDC_KEY` | `$BIND_CONF_DIR/rndc.key` | rndc key file path |
| `LOG_FILE` | *(auto)* | Path to a BIND log file to tail (containers) instead of `journalctl` |
| `WEBUI_PASSWORD` | *(empty = auth off)* | Shared password. **The webui facade must use the same value** so it can log in automatically. |
| `SECRET_KEY` | *(dev default)* | Secret used to sign the session cookie; set a random value |
| `SERVICE_NAME` | `bind9-webui` | Label on exported metrics |

> **Access protection:** set `WEBUI_PASSWORD` to require a password. The facade
> calls `/api/login` with this shared password on its own session and retries
> once on a 401, so you never type the password in the browser twice. If the
> variable is empty, authentication is disabled entirely.

---

## Security notes

- Authentication is a single shared password compared against the configured `WEBUI_PASSWORD` — nothing stored on disk, no user database.
- Sessions use a signed cookie (set `SECRET_KEY`!), with **brute-force lockout** (5 failed logins → 15 min block).
- rndc control channel is locked to loopback + private Docker subnets when the installer configures TCP.
- Restore writes go through the same validation gates BIND itself uses (`named-checkconf` / `named-checkzone`).
- `/healthz` and `/readyz` are open (probes); `/metrics` and every `/api/*` endpoint require auth when a password is set.
- No build step, no runtime downloads, no telemetry, no analytics.

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/login` | Login with the shared password |
| GET | `/api/session` | Auth state |
| POST | `/api/logout` | Log out |
| GET | `/api/status` | BIND9 server status (raw) |
| GET | `/api/status/structured` | Server status (parsed key-value) |
| GET | `/api/zones` | List all zones |
| GET | `/api/zone/<name>` | Zone detail + records + path + source |
| POST | `/api/zone` | Create zone (simple records or raw validated body) |
| POST | `/api/zone/preview` | Build a zone file for the wizard preview |
| DELETE | `/api/zone/<name>` | Delete zone |
| PUT | `/api/zone/<name>/file` | Update raw zone file |
| PUT | `/api/zone/<name>/records` | Bulk-update records |
| POST | `/api/zone/<name>/record` | Add record |
| DELETE | `/api/zone/<name>/record/<idx>` | Remove record |
| POST | `/api/zone/<name>/source` | Move zone between config files |
| POST | `/api/map-hosts` | Bulk-create A records from `IP host...` lines |
| GET | `/api/config/files` | List editable config files |
| GET | `/api/config/file/<name>` | Read config file |
| PUT | `/api/config/file/<name>` | Update config file |
| GET | `/api/config/check` | Run `named-checkconf` |
| GET | `/api/zone/<name>/check` | Run `named-checkzone` |
| GET | `/api/logs` | Query named logs |
| GET | `/api/backup` | Download config+zone tarball (gzip) |
| POST | `/api/restore` | Upload + validated restore |
| POST | `/api/dig` | Look up a name (`q`, `type`, `server`) |
| POST | `/api/control/reload` | rndc reload |
| POST | `/api/control/flush` | rndc flush |
| POST | `/api/control/stats` | rndc stats |
| POST | `/api/control/querylog` | Toggle query logging |
| GET | `/healthz` `/readyz` | Probes (open) |
| GET | `/metrics` | Prometheus metrics (auth-gated) |

---

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

pytest                      # full suite, no BIND required (rndc binary faked)
```

The suite covers auth + lockout, backup/restore, dig, the add-zone wizard
(preview + raw validation), config file CRUD, and the metrics/health probes.
CI runs on GitHub Actions for every push and PR.

---

## Project structure

```
bind9-webui/
├── app.py                  # Flask API — routes + auth + probes (no HTML)
├── bind_manager.py         # rndc commands + zone/config file parsing
├── metrics.py              # /healthz, /readyz, /metrics (Prometheus text)
├── tests/                  # pytest suite
├── requirements.txt        # flask
├── Dockerfile              # Container image (API only)
├── docker-compose.yml      # API container managing host/remote BIND over TCP rndc
├── docker-compose-w-bind9.yml  # Full stack: BIND9 container + API
├── docker/bind/            # Config/rndc.key shared with the BIND container
├── install.sh              # one-shot installer (fetch-based, --check safe)
└── bind9-webui.service     # Systemd unit file
```

## How it works

The API talks to BIND through the exact same tools an admin does:

- **`rndc`** — server control (status, reload, flush, stats, querylog); local UNIX socket on bare-metal, TCP 953 toward a container/remote BIND
- **Config files** — reads/writes `named.conf.local`, zone files under `/etc/bind` (or `/etc/named`)
- **`named-checkconf` / `named-checkzone`** — validation before writes land
- **`journalctl` / log file** — log viewing (containers tail `LOG_FILE`)

Transport is chosen from the environment: as a systemd service it uses the local
socket; inside a container it uses `RNDC_HOST` over TCP. No database. No magic.
The **[webui facade](https://github.com/himalsimkhada/webui)** holds the session
with this API (shared `WEBUI_PASSWORD`), proxies every dashboard call, and
renders the BIND9 management UI in the browser.

---

<div align="center">

**Poke around, file an issue, open a PR — feedback welcome.**

</div>

## License

MIT