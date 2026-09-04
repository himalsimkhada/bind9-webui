# Changelog

All notable changes to bind9-webui will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-09-04

### Added

- **Host Mapper** on the Zones tab — paste or upload lines of `IP host1 host2 ...` (or a `.txt`/`.hosts` file) and it bulk-creates A records in the matching existing zone for each host
  - Automatically resolves each host's zone (apex, subdomain, nested)
  - Skips duplicates, reports missing zones, and flags malformed lines
  - Host Mapper sits in a side-by-side panel next to the Zones table (stacks to one column on narrow screens)
- New API endpoint: `POST /api/map-hosts`

### Fixed

- **Zones could never actually load in BIND** — `add_zone` created an NS record (`ns1.<zone>`) without a matching A glue record, so `named-checkzone` failed with "NS has no address records" and the zone was "not loaded". New zones now include an `ns1` A record.

## [0.2.2] - 2026-09-04

### Added

- "Move to default-zones" / "Move back to local" buttons on zone detail — one-click relocation of a zone block between `named.conf.local` and `named.conf.default-zones` with automatic BIND reload
- Source indicator on zone detail showing which config file a zone lives in
- `protected` flag for built-in system zones (`localhost`, `127.in-addr.arpa`, `0.in-addr.arpa`, `255.in-addr.arpa`, `.`) that prevents accidental deletion
- New API endpoint: `POST /api/zone/<name>/source` to move zones between config files

### Changed

- Zone detail action buttons now use proper spacing via `.btn-row` layout
- Delete now works for user-created zones in default-zones (only built-in systems zones are protected)

## [0.2.1] - 2026-09-04

### Added

- Editable raw zone file in zone detail view (edit the full DNS zone file directly, then save + auto-reload BIND)
- Filesystem path display for each zone (e.g. `/etc/bind/db.example.com`)
- New API endpoint: `PUT /api/zone/<name>/file` to update raw zone file content

### Fixed

- Zone detail "Show Raw" now shows an editable textarea with Save and Revert actions

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
