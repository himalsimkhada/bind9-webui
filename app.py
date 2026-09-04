import os
from datetime import timedelta

from flask import Flask, jsonify, request, render_template, session
import bind_manager as bm

app = Flask(__name__)

# Password gate: if WEBUI_PASSWORD is empty/not set, authentication is disabled.
WEBUI_PASSWORD = os.environ.get("WEBUI_PASSWORD", "").strip()
app.secret_key = os.environ.get("SECRET_KEY", "bind9-webui-dev-secret-change-me")
# "Remember me" sessions auto-logout after 30 minutes.
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)


def is_authenticated():
    return bool(session.get("auth"))


def _ok(data=None, msg=None):
    r = {"ok": True}
    if data is not None:
        r["data"] = data
    if msg:
        r["message"] = msg
    return jsonify(r)


def _err(msg, code=400):
    return jsonify({"ok": False, "error": str(msg)}), code


@app.before_request
def protect_endpoints():
    # Only enforce when a password is configured.
    if not WEBUI_PASSWORD:
        return None
    # Allow the auth endpoints and static assets.
    if request.endpoint in ("index", "static", "api_login", "api_session"):
        return None
    if request.path.startswith("/api/") and not is_authenticated():
        return _err("Unauthorized", code=401)
    return None


@app.route("/")
def index():
    return render_template("index.html")


# ── Authentication ──────────────────────────────────────────────────────────

@app.route("/api/session")
def api_session():
    if not WEBUI_PASSWORD:
        return _ok({"auth": True, "auth_required": False})
    return _ok({"auth": is_authenticated(), "auth_required": True})


@app.route("/api/login", methods=["POST"])
def api_login():
    if not WEBUI_PASSWORD:
        return _err("Authentication is not enabled")
    data = request.json or {}
    password = data.get("password", "")
    if password != WEBUI_PASSWORD:
        return _err("Incorrect password", code=401)
    session["auth"] = True
    # Remember me -> persistent cookie that auto-expires in 30 minutes.
    session.permanent = bool(data.get("remember", False))
    session.permanent_session_lifetime = app.config["PERMANENT_SESSION_LIFETIME"]
    return _ok({"auth": True, "auth_required": True})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return _ok(msg="Logged out")


# ── Dashboard ───────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    try:
        return _ok(bm.get_status())
    except Exception as e:
        return _err(e)


@app.route("/api/status/structured")
def api_status_structured():
    try:
        return _ok(bm.get_status_structured())
    except Exception as e:
        return _err(e)


@app.route("/api/zones")
def api_zones():
    return _ok(bm.get_zones())


@app.route("/api/zone/<name>")
def api_zone_detail(name):
    try:
        text = bm.get_zone_file(name)
        path = bm.get_zone_path(name)
        zones = bm.get_zones()
        zone = next((z for z in zones if z["name"] == name), None)
        source = zone["source"] if zone else "unknown"
        protected = zone.get("protected", False) if zone else False
        records, soa = bm.parse_zone_records(text)
        return _ok({"zone": name, "records": records, "soa": soa, "raw": text,
                    "path": path, "source": source, "protected": protected})
    except Exception as e:
        return _err(e)


@app.route("/api/zone/<name>/file", methods=["PUT"])
def api_zone_update_file(name):
    data = request.json or {}
    content = data.get("content", "")
    try:
        path = bm.write_zone_file(name, content)
        return _ok(msg=f"Zone file saved to {path}")
    except Exception as e:
        return _err(e)


@app.route("/api/zone/<name>/source", methods=["POST"])
def api_zone_move_source(name):
    data = request.json or {}
    target = data.get("target", "default")
    try:
        bm.move_zone_source(name, target)
        return _ok(msg=f"Zone {name} moved to {target} config")
    except Exception as e:
        return _err(e)


@app.route("/api/map-hosts", methods=["POST"])
def api_map_hosts():
    data = request.json or {}
    text = data.get("text", "")
    if not text:
        return _err("No host lines provided")
    try:
        return _ok(bm.map_hosts(text))
    except Exception as e:
        return _err(e)


# ── Zone CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/zone", methods=["POST"])
def api_zone_create():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return _err("Zone name required")
    try:
        bm.add_zone(name, zone_type=data.get("type", "master"))
        return _ok(msg=f"Zone {name} created")
    except Exception as e:
        return _err(e)


@app.route("/api/zone/<name>", methods=["DELETE"])
def api_zone_delete(name):
    try:
        bm.remove_zone(name)
        return _ok(msg=f"Zone {name} removed")
    except Exception as e:
        return _err(e)


# ── Records ─────────────────────────────────────────────────────────────────

@app.route("/api/zone/<name>/records", methods=["PUT"])
def api_zone_update_records(name):
    data = request.json or {}
    records = data.get("records", [])
    try:
        bm.update_zone_records(name, records)
        return _ok(msg="Records updated")
    except Exception as e:
        return _err(e)


@app.route("/api/zone/<name>/record", methods=["POST"])
def api_record_add(name):
    data = request.json or {}
    required = ["name", "type", "value"]
    for f in required:
        if f not in data:
            return _err(f"Missing field: {f}")
    try:
        bm.add_record(name, data["name"], data["type"], data["value"],
                      ttl=data.get("ttl", 3600))
        return _ok(msg="Record added")
    except Exception as e:
        return _err(e)


@app.route("/api/zone/<name>/record/<int:idx>", methods=["DELETE"])
def api_record_delete(name, idx):
    try:
        bm.remove_record(name, idx)
        return _ok(msg="Record removed")
    except Exception as e:
        return _err(e)


# ── Configuration ───────────────────────────────────────────────────────────

CONF_FILES = {
    "named.conf": bm.NAMED_CONF,
    "named.conf.options": bm.NAMED_CONF_OPTIONS,
    "named.conf.local": bm.NAMED_CONF_LOCAL,
    "named.conf.default-zones": bm.NAMED_CONF_DEFAULT_ZONES,
}


@app.route("/api/config/files")
def api_config_files():
    return _ok(list(CONF_FILES.keys()))


@app.route("/api/config/file/<path:name>")
def api_config_get(name):
    path = CONF_FILES.get(name)
    if path is None:
        return _err("Unknown config file")
    return _ok(bm.read_conf_file(path))


@app.route("/api/config/file/<path:name>", methods=["PUT"])
def api_config_set(name):
    path = CONF_FILES.get(name)
    if path is None:
        return _err("Unknown config file")
    data = request.json or {}
    content = data.get("content", "")
    try:
        bm.write_conf_file(path, content)
        return _ok(msg=f"{name} saved")
    except Exception as e:
        return _err(e)


@app.route("/api/config/check")
def api_config_check():
    return _ok(bm.check_config())


@app.route("/api/zone/<name>/check")
def api_zone_check(name):
    try:
        return _ok(bm.check_zone(name))
    except Exception as e:
        return _err(e)


# ── Logs ────────────────────────────────────────────────────────────────────

@app.route("/api/logs")
def api_logs():
    lines = request.args.get("lines", 100, type=int)
    query = request.args.get("query", "")
    return _ok(bm.get_logs(lines=lines, query=query))


# ── rndc Controls ───────────────────────────────────────────────────────────

@app.route("/api/control/reload", methods=["POST"])
def api_reload():
    try:
        return _ok(bm.reload_config())
    except Exception as e:
        return _err(e)


@app.route("/api/control/flush", methods=["POST"])
def api_flush():
    try:
        return _ok(bm.flush_cache())
    except Exception as e:
        return _err(e)


@app.route("/api/control/stats", methods=["POST"])
def api_stats():
    try:
        return _ok(bm.get_stats())
    except Exception as e:
        return _err(e)


@app.route("/api/control/querylog", methods=["POST"])
def api_querylog():
    data = request.json or {}
    try:
        return _ok(bm.query_log(data.get("enable", True)))
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
