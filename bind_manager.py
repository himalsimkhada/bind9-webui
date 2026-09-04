import os
import re
import subprocess
from pathlib import Path

BIND_CONF_DIR = "/etc/bind"
NAMED_CONF = f"{BIND_CONF_DIR}/named.conf"
NAMED_CONF_OPTIONS = f"{BIND_CONF_DIR}/named.conf.options"
NAMED_CONF_LOCAL = f"{BIND_CONF_DIR}/named.conf.local"
NAMED_CONF_DEFAULT_ZONES = f"{BIND_CONF_DIR}/named.conf.default-zones"
ZONE_CACHE_DIR = "/var/cache/bind"
RNDCTIMEOUT = 5


def _run(cmd, check=False):
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=RNDCTIMEOUT
        )
        if check and r.returncode != 0:
            raise RuntimeError(r.stderr.strip() or f"Command failed: {cmd}")
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        raise RuntimeError("Command timed out")


def rndc(command):
    out, err, rc = _run(f"sudo rndc {command}")
    if rc != 0:
        raise RuntimeError(err or f"rndc {command} failed")
    return out


def _read_file(path):
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return ""
    except PermissionError:
        out, _, _ = _run(f"sudo cat {path}")
        return out


def _write_file(path, content):
    tmp = f"/tmp/bind_ui_{os.getpid()}.conf"
    Path(tmp).write_text(content)
    _run(f"sudo cp {tmp} {path}", check=True)
    _run(f"sudo chmod 644 {path}")
    os.unlink(tmp)


# ── Config File Read/Write ──────────────────────────────────────────────────

def read_conf_file(path):
    return _read_file(path)


def write_conf_file(path, content):
    _write_file(path, content)


# ── Config Parsing ──────────────────────────────────────────────────────────

def _strip_comments(text):
    text = re.sub(r'//.*', '', text)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text


def _find_block(text, keyword):
    pattern = re.compile(
        rf'{keyword}\s*(?:\"([^\"]*)\"\s*)?{{(.*?)}}',
        re.DOTALL
    )
    results = []
    for m in pattern.finditer(text):
        name = m.group(1) or ""
        body = m.group(2).strip()
        results.append((name, body))
    return results


def get_zones():
    zones = []
    raw_local = _strip_comments(_read_file(NAMED_CONF_LOCAL))
    raw_defaults = _strip_comments(_read_file(NAMED_CONF_DEFAULT_ZONES))

    protected_defaults = {"localhost", "127.in-addr.arpa", "0.in-addr.arpa",
                          "255.in-addr.arpa", "."}

    for source, text in [("local", raw_local), ("default", raw_defaults)]:
        for name, body in _find_block(text, "zone"):
            ftype = re.search(r'type\s+(\w+)', body)
            ffile = re.search(r'file\s+"([^"]+)"', body)
            zname = name.strip('"')
            zones.append({
                "name": zname,
                "type": ftype.group(1) if ftype else "unknown",
                "file": ffile.group(1) if ffile else "",
                "source": source,
                "protected": source == "default" and zname in protected_defaults,
            })
    return zones


def _resolve_zone_path(zone_file):
    if os.path.isabs(zone_file):
        return zone_file
    path = f"{BIND_CONF_DIR}/{zone_file}"
    if os.path.exists(path):
        return path
    path = f"{ZONE_CACHE_DIR}/{zone_file}"
    if os.path.exists(path):
        return path
    return f"{BIND_CONF_DIR}/{zone_file}"


def get_zone_file(zone_name):
    zones = get_zones()
    zone = next((z for z in zones if z["name"] == zone_name), None)
    if not zone:
        raise RuntimeError(f"Zone {zone_name} not found")
    return _read_file(_resolve_zone_path(zone['file']))


def get_zone_path(zone_name):
    zones = get_zones()
    zone = next((z for z in zones if z["name"] == zone_name), None)
    if not zone:
        raise RuntimeError(f"Zone {zone_name} not found")
    return _resolve_zone_path(zone['file'])


def write_zone_file(zone_name, content):
    content = content + "\n" if not content.endswith("\n") else content
    path = get_zone_path(zone_name)
    _write_file(path, content)
    rndc("reload")
    return path


def parse_zone_records(zone_text):
    records = []
    ttl_match = re.search(r'\$TTL\s+(\d+)', zone_text)
    default_ttl = int(ttl_match.group(1)) if ttl_match else 3600

    soa_match = re.search(
        r'@\s+IN\s+SOA\s+(\S+)\s+(\S+)\s*\((.*?)\)',
        zone_text, re.DOTALL
    )
    soa = None
    if soa_match:
        soa = {
            "primary_ns": soa_match.group(1),
            "admin_email": soa_match.group(2).replace(".", "@", 1) if "@" not in soa_match.group(2) else soa_match.group(2),
            "raw": soa_match.group(0),
        }

    for line in zone_text.splitlines():
        line = line.strip()
        if not line or line.startswith("$") or line.startswith(";") or line.startswith("(") or line.startswith(")"):
            continue
        if "SOA" in line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        if parts[0] in ("$TTL", "$ORIGIN"):
            continue
        name = parts[0]
        idx = 1
        ttl = default_ttl
        if parts[idx].isdigit():
            ttl = int(parts[idx])
            idx += 1
        if idx >= len(parts) or parts[idx] != "IN":
            continue
        idx += 1
        if idx >= len(parts):
            continue
        rtype = parts[idx]
        value = " ".join(parts[idx + 1:])
        records.append({
            "name": name,
            "ttl": ttl,
            "type": rtype,
            "value": value,
            "raw": line,
        })
    return records, soa


def build_zone_file(zone_name, records, soa=None, ttl=3600, origin=None):
    lines = []
    origin = origin or zone_name
    lines.append(f"$TTL {ttl}")
    lines.append(f"$ORIGIN {origin}.")
    lines.append("")

    if soa:
        lines.append(f"@ IN SOA {soa['primary_ns']} {soa['admin_email'].replace('@', '.')} (")
        lines.append("    2024010101  ; serial")
        lines.append("    3600        ; refresh")
        lines.append("    900         ; retry")
        lines.append("    604800      ; expire")
        lines.append("    86400       ; minimum")
        lines.append(")")
        lines.append("")

    for r in records:
        name = r.get("name", "@")
        rtype = r.get("type", "A")
        value = r.get("value", "")
        lines.append(f"{name}\tIN\t{rtype}\t{value}")

    lines.append("")
    return "\n".join(lines)


# ── Zone Management ─────────────────────────────────────────────────────────

def add_zone(zone_name, zone_type="master", records=None):
    zones = get_zones()
    if any(z["name"] == zone_name for z in zones):
        raise RuntimeError(f"Zone {zone_name} already exists")

    zone_file = f"db.{zone_name}"
    zone_path = f"{BIND_CONF_DIR}/{zone_file}"

    if records is None:
        records = [
            {"name": "@", "type": "NS", "value": f"ns1.{zone_name}.", "ttl": 3600},
            {"name": "ns1", "type": "A", "value": "127.0.0.1", "ttl": 3600},
        ]

    default_soa = {
        "primary_ns": f"ns1.{zone_name}.",
        "admin_email": f"admin.{zone_name}",
    }
    content = build_zone_file(zone_name, records, soa=default_soa)
    _write_file(zone_path, content)

    zone_block = f'zone "{zone_name}" {{\n    type {zone_type};\n    file "{BIND_CONF_DIR}/{zone_file}";\n}};\n\n'

    existing = _read_file(NAMED_CONF_LOCAL)
    _write_file(NAMED_CONF_LOCAL, existing + zone_block)

    rndc("reload")
    return True


def remove_zone(zone_name):
    zones = get_zones()
    zone = next((z for z in zones if z["name"] == zone_name), None)
    if not zone:
        raise RuntimeError(f"Zone {zone_name} not found")
    if zone.get("protected"):
        raise RuntimeError(f"'{zone_name}' is a protected system zone and cannot be deleted")

    conf = _read_file(NAMED_CONF_LOCAL)
    pattern = re.compile(
        rf'zone\s+"{re.escape(zone_name)}"\s*\{{.*?\}};\s*',
        re.DOTALL
    )
    new_conf = pattern.sub("", conf)
    _write_file(NAMED_CONF_LOCAL, new_conf)

    defaults_conf = _read_file(NAMED_CONF_DEFAULT_ZONES)
    new_defaults_conf = pattern.sub("", defaults_conf)
    if new_defaults_conf != defaults_conf:
        _write_file(NAMED_CONF_DEFAULT_ZONES, new_defaults_conf)

    if zone["file"]:
        fpath = _resolve_zone_path(zone['file'])
        if os.path.exists(fpath) and fpath.startswith(BIND_CONF_DIR):
            _run(f"sudo rm {fpath}")

    rndc("reload")
    return True


def move_zone_source(zone_name, target):
    zones = get_zones()
    zone = next((z for z in zones if z["name"] == zone_name), None)
    if not zone:
        raise RuntimeError(f"Zone {zone_name} not found")

    if target not in ("default", "local"):
        raise RuntimeError("Target must be 'default' or 'local'")

    if zone["source"] == target:
        raise RuntimeError(f"Zone {zone_name} is already in {target} config")

    pattern = re.compile(
        rf'zone\s+"{re.escape(zone_name)}"\s*\{{.*?\}};\s*',
        re.DOTALL
    )

    from_conf = NAMED_CONF_LOCAL if zone["source"] == "local" else NAMED_CONF_DEFAULT_ZONES
    to_conf = NAMED_CONF_LOCAL if target == "local" else NAMED_CONF_DEFAULT_ZONES

    block_match = re.search(
        rf'zone\s+"{re.escape(zone_name)}"\s*\{{.*?\}};\s*',
        _read_file(from_conf), re.DOTALL
    )
    if not block_match:
        raise RuntimeError(f"Could not find zone block for {zone_name}")

    block = block_match.group(0)

    src = _read_file(from_conf)
    new_src = pattern.sub("", src)
    _write_file(from_conf, new_src)

    dst = _read_file(to_conf)
    _write_file(to_conf, dst.rstrip() + "\n\n" + block)

    rndc("reload")
    return True


def update_zone_records(zone_name, records):
    zones = get_zones()
    zone = next((z for z in zones if z["name"] == zone_name), None)
    if not zone:
        raise RuntimeError(f"Zone {zone_name} not found")

    soa = {
        "primary_ns": f"ns1.{zone_name}.",
        "admin_email": f"admin.{zone_name}",
    }

    existing_text = get_zone_file(zone_name)
    existing_records, existing_soa = parse_zone_records(existing_text)
    if existing_soa:
        soa = existing_soa

    content = build_zone_file(zone_name, records, soa=soa)

    zone_path = _resolve_zone_path(zone['file'])
    _write_file(zone_path, content)

    rndc("reload")
    return True


def add_record(zone_name, name, rtype, value, ttl=3600):
    existing_text = get_zone_file(zone_name)
    records, soa = parse_zone_records(existing_text)

    records.append({
        "name": name,
        "ttl": ttl,
        "type": rtype,
        "value": value,
    })

    return update_zone_records(zone_name, records)


def remove_record(zone_name, record_index):
    existing_text = get_zone_file(zone_name)
    records, soa = parse_zone_records(existing_text)

    if record_index < 0 or record_index >= len(records):
        raise RuntimeError("Invalid record index")

    records.pop(record_index)
    return update_zone_records(zone_name, records)


# ── Bulk Host Mapping ────────────────────────────────────────────────────────

def _find_zone_for_host(host, zone_names):
    host = host.rstrip(".").lower()
    labels = host.split(".")
    for i in range(len(labels)):
        zone = ".".join(labels[i:])
        if zone in zone_names:
            name = ".".join(labels[:i]) if i > 0 else "@"
            return zone, name
    return None, None


def map_hosts(text):
    zones = get_zones()
    zone_names = set(z["name"] for z in zones)
    results = []

    created_hosts = set()
    missing_zones = {}
    duplicate_skips = 0
    bad_lines = 0
    created_count = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = line.split()
        if len(parts) < 2:
            bad_lines += 1
            results.append({"type": "SKIP", "line": line, "message": "no IP + host"})
            continue
        ip = parts[0]
        hosts = parts[1:]

        if not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip) and not re.match(r'^[0-9a-fA-F:]+$', ip):
            bad_lines += 1
            results.append({"type": "SKIP", "line": line, "message": f"unrecognized IP: {ip}"})
            continue

        for host in hosts:
            zone, name = _find_zone_for_host(host, zone_names)
            if not zone:
                missing_zones.setdefault(host, []).append(host)
                results.append({"type": "NO_ZONE", "host": host, "ip": ip,
                                "message": f"no matching zone found for '{host}'"})
                continue

            key = (ip, host)
            if key in created_hosts:
                duplicate_skips += 1
                results.append({"type": "DUP", "zone": zone, "host": host, "ip": ip,
                                "message": "already added"})
                continue
            created_hosts.add(key)

            try:
                add_record(zone, name, "A", ip)
                created_count += 1
                results.append({"type": "ADD", "zone": zone, "host": host, "name": name, "ip": ip,
                                "message": f"A record {host} -> {ip} (zone {zone}, name {name})"})
            except Exception as e:
                results.append({"type": "ERROR", "zone": zone, "host": host, "ip": ip,
                                "message": str(e)})

    return {
        "results": results,
        "summary": {
            "created": created_count,
            "duplicates_skipped": duplicate_skips,
            "missing_zones": len(missing_zones),
            "bad_lines": bad_lines,
            "missing_zone_names": sorted(missing_zones.keys()),
        },
    }


# ── rndc Controls ───────────────────────────────────────────────────────────

def reload_config():
    return rndc("reload")


def reload_zone(zone_name):
    return rndc(f"reload zone {zone_name}")


def flush_cache():
    return rndc("flush")


def get_stats():
    out, _, rc = _run("sudo rndc stats")
    stats_file = "/var/cache/bind/named.stats"
    content = _read_file(stats_file)
    return content


def get_status():
    out, _, rc = _run("sudo rndc status")
    return out


def get_status_structured():
    raw = get_status()
    info = {}
    mapping = {
        "version": "version",
        "running on": "host",
        "boot time": "boot_time",
        "last configured": "last_configured",
        "configuration file": "config_file",
        "CPUs found": "cpus",
        "worker threads": "workers",
        "number of zones": "zones",
        "debug level": "debug_level",
        "xfers running": "xfers_running",
        "xfers deferred": "xfers_deferred",
        "soa queries in progress": "soa_queries",
        "query logging is": "query_logging",
        "recursive clients": "recursive_clients",
        "tcp clients": "tcp_clients",
        "TCP high-water": "tcp_highwater",
        "server is up and running": "running",
    }
    for line in raw.splitlines():
        line = line.strip()
        for key, field in mapping.items():
            if line.lower().startswith(key):
                value = line[len(key):].strip(": ")
                if field == "running":
                    value = True
                info[field] = value
    return info


def query_log(status=True):
    cmd = "querylog on" if status else "querylog off"
    return rndc(cmd)


# ── Logs ────────────────────────────────────────────────────────────────────

def get_logs(lines=100, query=""):
    cmd = f"sudo journalctl -u named --no-pager -n {lines}"
    if query:
        cmd += f" | grep -i '{query}'"
    out, _, _ = _run(cmd)
    if not out:
        out, _, _ = _run(f"sudo tail -n {lines} /var/log/syslog 2>/dev/null | grep -i named")
    if not out:
        out = "No logs found. Ensure named is running as a systemd service."
    return out


# ── Validation ──────────────────────────────────────────────────────────────

def check_config():
    out, err, rc = _run("sudo named-checkconf /etc/bind/named.conf")
    return {"valid": rc == 0, "error": err or out}


def check_zone(zone_name):
    zones = get_zones()
    zone = next((z for z in zones if z["name"] == zone_name), None)
    if not zone:
        raise RuntimeError(f"Zone {zone_name} not found")

    zone_path = _resolve_zone_path(zone['file'])
    out, err, rc = _run(f"sudo named-checkzone {zone_name} {zone_path}")
    return {"valid": rc == 0, "output": out, "error": err}
