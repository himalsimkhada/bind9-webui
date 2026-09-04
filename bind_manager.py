import os
import re
import subprocess
import time
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


def get_options():
    raw = _strip_comments(_read_file(NAMED_CONF_OPTIONS))
    return raw


def set_options(content):
    _write_file(NAMED_CONF_OPTIONS, content)


def get_zones():
    zones = []
    raw_local = _strip_comments(_read_file(NAMED_CONF_LOCAL))
    raw_defaults = _strip_comments(_read_file(NAMED_CONF_DEFAULT_ZONES))

    for source, text in [("local", raw_local), ("default", raw_defaults)]:
        for name, body in _find_block(text, "zone"):
            ftype = re.search(r'type\s+(\w+)', body)
            ffile = re.search(r'file\s+"([^"]+)"', body)
            zones.append({
                "name": name.strip('"'),
                "type": ftype.group(1) if ftype else "unknown",
                "file": ffile.group(1) if ffile else "",
                "source": source,
            })
    return zones


def _resolve_zone_path(zone_file):
    if os.path.isabs(zone_file):
        if os.path.exists(zone_file):
            return zone_file
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
    if zone["source"] == "default":
        raise RuntimeError("Cannot remove default zones")

    conf = _read_file(NAMED_CONF_LOCAL)
    pattern = re.compile(
        rf'zone\s+"{re.escape(zone_name)}"\s*\{{.*?\}};\s*',
        re.DOTALL
    )
    new_conf = pattern.sub("", conf)
    _write_file(NAMED_CONF_LOCAL, new_conf)

    if zone["file"]:
        fpath = _resolve_zone_path(zone['file'])
        if os.path.exists(fpath):
            _run(f"sudo rm {fpath}")

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


def query_log(status=True):
    cmd = "querylog on" if status else "querylog off"
    return rndc(cmd)


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
