"""Tests for the Flask app: auth, lockout, and the new API surfaces."""
import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as a  # noqa: E402

PASSWORD = "test-password-123"


@pytest.fixture()
def client():
    a.WEBUI_PASSWORD = PASSWORD
    a._login_failures.clear()
    a._login_locked_until.clear()
    a.app.config["TESTING"] = True
    return a.app.test_client()


def _login(client, password=PASSWORD, remember=False):
    return client.post("/api/login", json={"password": password, "remember": remember})


# ── Authentication ──────────────────────────────────────────────────────

def test_api_requires_auth(client):
    r = client.get("/api/zones")
    assert r.status_code == 401
    assert r.get_json()["error"] == "Unauthorized"


def test_login_wrong_password(client):
    r = _login(client, password="wrong")
    assert r.status_code == 401


def test_login_ok_and_session(client):
    r = _login(client)
    assert r.status_code == 200
    assert r.get_json()["data"]["auth"] is True
    r = client.get("/api/session")
    assert r.get_json()["data"]["auth"] is True


def test_logout_clears_session(client):
    _login(client)
    client.post("/api/logout")
    r = client.get("/api/session")
    assert r.get_json()["data"]["auth"] is False


def test_auth_disabled_when_no_password(client):
    a.WEBUI_PASSWORD = ""
    r = client.get("/api/session")
    assert r.get_json()["data"]["auth_required"] is False
    r = client.get("/api/zones")
    assert r.status_code in (200, 400)  # bypasses the 401 gate entirely


def test_lockout_after_failures(client):
    for _ in range(5):
        _login(client, password="wrong")
    r = _login(client, password=PASSWORD)  # correct password but locked out
    assert r.status_code == 429
    assert "Too many failed attempts" in r.get_json()["error"]
    # still locked for subsequent tries
    r = client.get("/api/session")
    assert r.get_json()["data"]["auth"] is False


def test_success_resets_lockout(client):
    _login(client, password="wrong")
    _login(client, password="wrong")
    r = _login(client, password=PASSWORD)
    assert r.status_code == 200
    for _ in range(4):
        _login(client, password="wrong")
    r = _login(client, password="wrong")
    assert r.status_code == 401  # not locked because failures were pruned, limit not hit yet


# ── Backup ──────────────────────────────────────────────────────────────

def test_backup_requires_auth(client):
    r = client.get("/api/backup")
    assert r.status_code == 401


def test_backup_returns_gzip(client, monkeypatch):
    monkeypatch.setattr(a.bm, "backup_data", lambda: b"\x1f\x8b-fake-bytes")
    _login(client)
    r = client.get("/api/backup")
    assert r.status_code == 200
    assert r.mimetype == "application/gzip"
    assert r.data == b"\x1f\x8b-fake-bytes"


def test_restore_calls_backend(client, monkeypatch):
    _login(client)
    calls = {}

    def fake_restore(data, **kwargs):
        calls["data"] = data
        return {"config_files": 4, "zone_files": 10}

    monkeypatch.setattr(a.bm, "restore_backup", fake_restore)
    r = client.post("/api/restore", data={"file": (io.BytesIO(b"PK-data"), "backup.tar.gz")},
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert calls["data"] == b"PK-data"


def test_restore_missing_file(client):
    _login(client)
    r = client.post("/api/restore", data={}, content_type="multipart/form-data")
    assert r.status_code == 400


# ── Dig ────────────────────────────────────────────────────────────────

def test_dig_calls_backend(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(a.bm, "dig", lambda q, rtype="A", server=None: {
        "query": q, "type": rtype, "server": server or "host", "output": "answer", "rc": 0})
    r = client.post("/api/dig", json={"q": "example.com", "type": "MX"})
    assert r.status_code == 200
    body = r.get_json()["data"]
    assert body["query"] == "example.com"
    assert body["type"] == "MX"


def test_dig_requires_query(client):
    _login(client)
    r = client.post("/api/dig", json={})
    assert r.status_code == 400


# ── Zone create / preview wizard ───────────────────────────────────────

def test_zone_preview_returns_body(client):
    _login(client)
    r = client.post("/api/zone/preview", json={
        "name": "example.com",
        "ttl": 3600,
        "records": [{"name": "www", "type": "A", "value": "10.0.0.1"}],
    })
    assert r.status_code == 200
    body = r.get_json()["data"]["body"]
    assert "$ORIGIN example.com." in body
    assert "$TTL 3600" in body
    assert "www\tIN\tA\t10.0.0.1" in body


def test_zone_create_rejects_invalid_name(client):
    _login(client)
    r = client.post("/api/zone", json={"name": "bad name!",
                                       "ttl": 3600,
                                       "records": []})
    assert r.status_code == 400
    assert "Invalid zone name" in r.get_json()["error"]


def test_zone_create_raw_valid_body(client, monkeypatch):
    _login(client)
    calls = {}
    monkeypatch.setattr(a.bm, "validate_zone_body",
                        lambda name, body: {"valid": True, "output": "OK", "error": ""})

    def fake_add(name, **kw):
        calls.update({"name": name, **kw})

    monkeypatch.setattr(a.bm, "add_zone", fake_add)
    r = client.post("/api/zone", json={"name": "raw.example.com", "body": "$TTL 3600\n"})
    assert r.status_code == 200
    assert calls["name"] == "raw.example.com"
    assert calls["body"] == "$TTL 3600\n"
    assert calls["zone_type"] == "master"


def test_zone_create_raw_invalid_body(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(a.bm, "validate_zone_body",
                        lambda name, body: {"valid": False, "output": "", "error": "bad zone file"})

    def fake_add(name, **kw):
        raise AssertionError("add_zone must not be called for an invalid body")

    monkeypatch.setattr(a.bm, "add_zone", fake_add)
    r = client.post("/api/zone", json={"name": "raw.example.com", "body": "garbage"})
    assert r.status_code == 400
    assert "Zone file invalid" in r.get_json()["error"]