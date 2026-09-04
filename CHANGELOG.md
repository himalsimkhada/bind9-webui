# Changelog

All notable changes to bind9-webui will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-09-04

### Added

- Dark/light mode toggle (persisted in localStorage)
- Logs tab with journalctl/syslog viewer, line count control, and text filtering
- Syntax highlighting for log entries (errors in red, warnings in yellow)
- Configuration tab with tabs for all conf files: `named.conf`, `named.conf.options`, `named.conf.local`, `named.conf.default-zones`
- Structured server status on dashboard (stat boxes for status, version, zones, workers, boot time, query log)
- Raw output toggle for server status
- New API endpoints: `/api/status/structured`, `/api/config/files`, `/api/config/file/<name>`, `/api/logs`

### Changed

- Config tab renamed to "Configuration"
- named.conf.options now shows full content including comments (no longer stripped)
- Dashboard redesigned with stat grid layout

## [0.1.0] - 2026-09-04

### Added

- Dashboard with BIND9 server status display
- rndc controls: reload config, flush cache, stats, querylog toggle
- Zone management: list, create, delete zones
- Record management: add/remove A, AAAA, MX, CNAME, NS, TXT, SRV, PTR records
- Zone file viewer (raw view toggle)
- Zone validation via `named-checkzone`
- Config validation via `named-checkconf`
- named.conf.options editor with save
- Dark minimal UI with monospace terminal aesthetic
- `install.sh` setup script for one-shot installation
- Systemd service file for auto-start on boot
- Full REST API for all operations

### Known Limitations

- Requires `sudo` access for rndc and BIND config file operations
- No authentication — do not expose to untrusted networks
- Flask development server used (suitable for LAN/lab, not public internet)
