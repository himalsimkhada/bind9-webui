from flask import Flask, jsonify, request, render_template
import bind_manager as bm

app = Flask(__name__)


def _ok(data=None, msg=None):
    r = {"ok": True}
    if data is not None:
        r["data"] = data
    if msg:
        r["message"] = msg
    return jsonify(r)


def _err(msg, code=400):
    return jsonify({"ok": False, "error": str(msg)}), code


@app.route("/")
def index():
    return render_template("index.html")


# ── Dashboard ───────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    try:
        return _ok(bm.get_status())
    except Exception as e:
        return _err(e)


@app.route("/api/zones")
def api_zones():
    return _ok(bm.get_zones())


@app.route("/api/zone/<name>")
def api_zone_detail(name):
    try:
        text = bm.get_zone_file(name)
        records, soa = bm.parse_zone_records(text)
        return _ok({"zone": name, "records": records, "soa": soa, "raw": text})
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


# ── Config ──────────────────────────────────────────────────────────────────

@app.route("/api/config/options")
def api_config_options():
    return _ok(bm.get_options())


@app.route("/api/config/options", methods=["PUT"])
def api_config_options_set():
    data = request.json or {}
    content = data.get("content", "")
    try:
        bm.set_options(content)
        return _ok(msg="Options updated")
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
