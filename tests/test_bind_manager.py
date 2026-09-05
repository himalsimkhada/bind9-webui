"""Tests for bind_manager parsing / pure logic (no live named required)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bind_manager as bm  # noqa: E402

SAMPLE_ZONE = """$TTL 3600
$ORIGIN example.com.
@ IN SOA ns1.example.com. admin.example.com (
    2024010101  ; serial
    3600        ; refresh
    900         ; retry
    604800      ; expire
    86400       ; minimum
)
@ IN NS ns1.example.com.
@ IN NS ns2.example.com.
@ IN A 10.0.0.1
www IN A 10.0.0.2
www IN A 10.0.0.3
mail IN MX 10 mail.example.com.
"""


def test_parse_zone_records():
    records, soa = bm.parse_zone_records(SAMPLE_ZONE)
    assert soa is not None
    assert soa["primary_ns"] == "ns1.example.com."
    types = [(r["name"], r["type"]) for r in records]
    assert ("@", "NS") in types
    assert ("@", "A") in types
    assert ("www", "A") in types
    # both A records for www survive (multi-valued names)
    a_records = [r for r in records if r["name"] == "www" and r["type"] == "A"]
    assert len(a_records) == 2
    assert a_records[0]["value"] == "10.0.0.2"
    assert a_records[1]["value"] == "10.0.0.3"


def test_parse_zone_records_default_ttl():
    minimal = "@ IN A 1.2.3.4\nhost IN NS ns.x.\n"
    records, _ = bm.parse_zone_records(minimal)
    assert all(r["ttl"] == 3600 for r in records)


def test_build_zone_file_contains_entries():
    records = [
        {"name": "@", "type": "A", "value": "10.0.0.1"},
        {"name": "www", "type": "A", "value": "10.0.0.2"},
    ]
    text = bm.build_zone_file("example.com", records,
                              soa={"primary_ns": "ns1.example.com.",
                                   "admin_email": "admin.example.com"})
    assert "$TTL 3600" in text
    assert "@ IN SOA ns1.example.com. admin.example.com" in text
    assert "@\tIN\tA\t10.0.0.1" in text
    assert "www\tIN\tA\t10.0.0.2" in text


@pytest.mark.parametrize("host,zones,expected", [
    ("www.example.com", {"example.com"}, ("example.com", "www")),
    ("example.com", {"example.com"}, ("example.com", "@")),
    ("api.www.example.com", {"www.example.com", "example.com"}, ("www.example.com", "api")),
    ("other.net", {"example.com"}, (None, None)),
    ("EXAMPLE.COM.", {"example.com"}, ("example.com", "@")),
    ("sub.example.com", {"example.com", "sub.example.com"}, ("sub.example.com", "@")),
])
def test_find_zone_for_host(host, zones, expected):
    assert bm._find_zone_for_host(host, zones) == expected


def test_map_hosts(monkeypatch):
    monkeypatch.setattr(bm, "get_zones", lambda: [
        {"name": "example.com"},
        {"name": "himal.com"},
    ])
    added = []
    monkeypatch.setattr(bm, "add_record", lambda zone, name, rtype, value: added.append((zone, name, value)))

    res = bm.map_hosts("10.1.1.1 www.example.com api.example.com\n"
                       "10.1.1.2 foo.unknown.net\n"
                       "# comment\n"
                       "10.2.2.2 example.com\n")
    s = res["summary"]
    assert s["created"] == 3          # www + api in example.com, @ in example.com
    assert s["duplicates_skipped"] == 0
    assert s["bad_lines"] == 0
    assert s["missing_zones"] == 1    # foo.unknown.net
    assert "foo.unknown.net" in s["missing_zone_names"]
    assert ("example.com", "www", "10.1.1.1") in added
    assert ("example.com", "@", "10.2.2.2") in added


def test_map_hosts_duplicate_skip(monkeypatch):
    monkeypatch.setattr(bm, "get_zones", lambda: [{"name": "example.com"}])
    added = []
    monkeypatch.setattr(bm, "add_record", lambda zone, name, rtype, value: added.append(1))
    res = bm.map_hosts("10.1.1.1 www.example.com\n10.1.1.1 www.example.com\n")
    assert res["summary"]["created"] == 1
    assert res["summary"]["duplicates_skipped"] == 1


# ── Backup / Restore ────────────────────────────────────────────────────

def _make_tarball(members):
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, payload in members.items():
            info = tarfile.TarInfo(name=name)
            data = payload.encode()
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_backup_contains_config_and_zones(monkeypatch, tmp_path):
    conf = tmp_path / "named.conf"
    conf.write_text("options { };\n")
    zone_file = tmp_path / "db.example.com"
    zone_file.write_text("$TTL 3600\n")
    monkeypatch.setattr(bm, "BACKUP_MEMBERS", {"named.conf": str(conf)})
    monkeypatch.setattr(bm, "get_zones", lambda: [{"name": "example.com", "file": str(zone_file)}])
    monkeypatch.setattr(bm, "_resolve_zone_path", lambda f: f)
    monkeypatch.setenv("RNDC_KEY", str(tmp_path / "rndc.key"))
    (tmp_path / "rndc.key").write_text("key fake\n")

    data = bm.backup_data()
    assert data[:2] == b"\x1f\x8b"  # gzip magic
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        names = {m.name for m in tf.getmembers()}
    assert "bind-config/named.conf" in names
    assert "zones/db.example.com" in names
    assert "keys/rndc.key" in names


def test_restore_applies_config_files(monkeypatch, tmp_path):
    conf = tmp_path / "named.conf"
    conf.write_text("options { };\n")
    zone_file = tmp_path / "db.example.com"
    zone_file.write_text("$TTL 3600\n")
    monkeypatch.setattr(bm, "BACKUP_MEMBERS", {"named.conf": str(conf)})
    monkeypatch.setattr(bm, "get_zones", lambda: [{"name": "example.com", "file": str(zone_file)}])
    monkeypatch.setattr(bm, "_resolve_zone_path", lambda f: f)
    monkeypatch.setenv("RNDC_KEY", str(tmp_path / "rndc.key"))
    (tmp_path / "rndc.key").write_text("key fake\n")
    written = {}
    monkeypatch.setattr(bm, "_write_file", lambda path, content: written.__setitem__(str(path), content))
    monkeypatch.setattr(bm, "_chown_zone", lambda path: None)
    monkeypatch.setattr(bm, "check_config", lambda: {"valid": True, "error": ""})
    monkeypatch.setattr(bm, "rndc", lambda cmd: "ok")
    monkeypatch.setattr(bm, "_run", lambda *a, **k: ("", "", 0))

    data = bm.backup_data()
    written.clear()
    res = bm.restore_backup(data)
    assert res["config_files"] == 1
    assert res["zone_files"] == 1
    assert str(conf) in written
    assert str(zone_file) in written


def test_restore_rolls_back_on_bad_config(monkeypatch, tmp_path):
    conf = tmp_path / "named.conf"
    conf.write_text("GARBAGE THAT WILL BE REPLACED\n")
    monkeypatch.setattr(bm, "BACKUP_MEMBERS", {"named.conf": str(conf)})
    monkeypatch.setattr(bm, "get_zones", lambda: [])
    written = {}
    monkeypatch.setattr(bm, "_write_file", lambda path, content: written.__setitem__(str(path), content))
    monkeypatch.setattr(bm, "_chown_zone", lambda path: None)
    monkeypatch.setattr(bm, "check_config", lambda: {"valid": False, "error": "syntax error"})
    monkeypatch.setattr(bm, "_run", lambda *a, **k: ("", "", 0))

    bad = _make_tarball({"bind-config/named.conf": "new-content"})
    with pytest.raises(RuntimeError, match="named-checkconf"):
        bm.restore_backup(bad)


def test_restore_rejects_tarball_without_named_conf(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "get_zones", lambda: [])
    bad = _make_tarball({"random.txt": "hi"})
    with pytest.raises(RuntimeError, match="does not contain a named.conf"):
        bm.restore_backup(bad)