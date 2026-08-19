import hashlib
import json
from pathlib import Path

import pytest
import investment_audit.catalog.backup_manifest as backup_manifest

from investment_audit.catalog.backup_manifest import (
    create_manifest,
    verify_manifest,
    write_manifest,
)
from investment_audit.catalog.schema_export import CATALOG_QUERIES, export_catalog, write_catalog
from scripts.investment_audit import main


class FakeCursor:
    def __init__(self, rows_by_marker):
        self.rows_by_marker = rows_by_marker
        self.description = []
        self._rows = []
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)
        marker = next((key for key in self.rows_by_marker if key in sql), None)
        columns, self._rows = self.rows_by_marker.get(marker, ([], []))
        self.description = [(column,) for column in columns]

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows_by_marker):
        self.cursor_instance = FakeCursor(rows_by_marker)

    def cursor(self):
        return self.cursor_instance


def test_catalog_queries_cover_required_postgres_objects_and_are_read_only():
    assert set(CATALOG_QUERIES) == {
        "tables", "columns", "constraints", "indexes", "triggers", "views",
        "sequences", "functions", "extensions", "owners", "grants",
    }
    forbidden = ("insert ", "update ", "delete ", "alter ", "drop ", "create ")
    for sql in CATALOG_QUERIES.values():
        normalized = " ".join(sql.lower().split())
        assert normalized.startswith("select ") or normalized.startswith("with ")
        assert not any(token in normalized for token in forbidden)


def test_catalog_export_is_deterministic_and_has_sha256(tmp_path):
    connection = FakeConnection({
        "/* tables */": (["schema", "name"], [("public", "z"), ("public", "a")]),
        "/* columns */": (["name", "position"], [("id", 1)]),
    })

    first = export_catalog(connection)
    second = export_catalog(connection)

    assert first == second
    assert [row["name"] for row in first["catalog"]["tables"]] == ["a", "z"]
    expected = hashlib.sha256(
        json.dumps(first["catalog"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    assert first["sha256"] == expected
    output = tmp_path / "catalog.json"
    write_catalog(connection, output)
    assert json.loads(output.read_text(encoding="utf-8"))["sha256"] == expected


def test_manifest_hashes_existing_files_deterministically_without_secret_paths(tmp_path):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    (dumps / "b.dump").write_bytes(b"beta")
    (dumps / "a.dump").write_bytes(b"alpha")

    manifest = create_manifest([dumps / "b.dump", dumps / "a.dump"], base_dir=dumps)

    assert [item["path"] for item in manifest["files"]] == ["a.dump", "b.dump"]
    assert manifest["files"][0]["sha256"] == hashlib.sha256(b"alpha").hexdigest()
    assert str(tmp_path) not in json.dumps(manifest)
    assert "password" not in json.dumps(manifest).lower()


def test_manifest_verification_detects_changed_and_missing_files(tmp_path):
    dumps = tmp_path / "dumps"
    dumps.mkdir()
    first = dumps / "first.dump"
    second = dumps / "second.dump"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    manifest_path = tmp_path / "manifest.json"
    write_manifest([first, second], manifest_path, base_dir=dumps)

    assert verify_manifest(manifest_path, base_dir=dumps)["ok"] is True
    first.write_bytes(b"changed")
    second.unlink()
    result = verify_manifest(manifest_path, base_dir=dumps)
    assert result["ok"] is False
    assert result["changed"] == ["first.dump"]
    assert result["missing"] == ["second.dump"]


def test_manifest_rejects_missing_inputs_and_paths_outside_base(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.dump"
    outside.write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        create_manifest([base / "missing.dump"], base_dir=base)
    with pytest.raises(ValueError):
        create_manifest([outside], base_dir=base)


def test_cli_manifest_defaults_to_dry_run_and_execute_writes(tmp_path, capsys):
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"safe")
    output = tmp_path / "manifest.json"
    args = ["backup-manifest", "--base-dir", str(tmp_path), "--output", str(output), str(dump)]
    assert main(args) == 0
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["dry_run"] is True

    assert main([*args, "--execute"]) == 0
    assert output.exists()


def test_cli_catalog_dry_run_does_not_connect_or_echo_dsn(tmp_path, capsys, monkeypatch):
    secret_dsn = "postgresql://user:secret@example/db"
    monkeypatch.setenv("AUDIT_TEST_DSN", secret_dsn)
    called = False

    def connector(_dsn):
        nonlocal called
        called = True
        raise AssertionError("dry run must not connect")

    result = main([
        "catalog-export", "--dsn-env", "AUDIT_TEST_DSN", "--output", str(tmp_path / "catalog.json")
    ], connect=connector)
    output = capsys.readouterr().out
    assert result == 0
    assert called is False
    assert secret_dsn not in output
    assert "secret" not in output


def test_cli_catalog_sanitizes_connection_errors(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("AUDIT_TEST_DSN", "postgresql://user:super-secret@host/db")
    def connector(_dsn):
        raise RuntimeError("password=super-secret")

    result = main([
        "catalog-export", "--dsn-env", "AUDIT_TEST_DSN",
        "--output", str(tmp_path / "catalog.json"), "--execute",
    ], connect=connector)
    captured = capsys.readouterr()
    assert result == 2
    assert "super-secret" not in captured.err


def test_cli_rejects_credential_bearing_dsn_argument(tmp_path):
    with pytest.raises(SystemExit):
        main(["catalog-export", "--dsn", "postgresql://user:secret@host/db",
              "--output", str(tmp_path / "catalog.json")])


def test_manifest_rejects_symlink_input(tmp_path, monkeypatch):
    target = tmp_path / "target.dump"
    link = tmp_path / "link.dump"
    target.write_bytes(b"dump")
    original_is_symlink = type(link).is_symlink
    monkeypatch.setattr(
        type(link), "is_symlink", lambda path: path == link or original_is_symlink(path)
    )
    with pytest.raises(ValueError, match="link"):
        create_manifest([link], base_dir=tmp_path)


def test_manifest_rejects_file_changed_while_hashing(tmp_path, monkeypatch):
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"stable")
    real_fstat = backup_manifest.os.fstat
    calls = 0

    def changing_fstat(fd):
        nonlocal calls
        calls += 1
        result = real_fstat(fd)
        if calls == 2:
            dump.write_bytes(b"changed-during-read")
            result = real_fstat(fd)
        return result

    monkeypatch.setattr(backup_manifest.os, "fstat", changing_fstat)
    with pytest.raises(RuntimeError, match="changed while hashing"):
        create_manifest([dump], base_dir=tmp_path)
