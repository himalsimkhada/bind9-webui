# Changelog

All notable changes to bind9-webui will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
