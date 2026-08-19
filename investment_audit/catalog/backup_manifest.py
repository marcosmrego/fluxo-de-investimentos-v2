"""Hash existing database dump files and verify their integrity."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Iterable


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _ensure_no_links(path: Path, base: Path) -> None:
    current = base
    relative = path.relative_to(base)
    for part in relative.parts:
        current = current / part
        if _is_link_or_junction(current):
            raise ValueError(f"symbolic link or junction is not allowed: {relative.as_posix()}")


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _sha256(path: Path, base: Path) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"not a regular file: {path}")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after):
            raise RuntimeError(f"file changed while hashing: {path}")
        _ensure_no_links(path, base)
        current = path.stat(follow_symlinks=False)
        if _file_identity(before) != _file_identity(current):
            raise RuntimeError(f"file changed while hashing: {path}")
        return before.st_size, digest.hexdigest()
    finally:
        os.close(descriptor)


def _relative_file(path: str | Path, base_dir: Path) -> tuple[Path, str]:
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError(f"file is outside base directory: {path}") from exc
    _ensure_no_links(candidate, base_dir)
    if not candidate.exists():
        raise FileNotFoundError(candidate)
    return candidate, relative.as_posix()


def create_manifest(files: Iterable[str | Path], *, base_dir: str | Path) -> dict:
    """Create an in-memory manifest. No backup commands are executed."""
    base = Path(base_dir).resolve(strict=True)
    entries = []
    for item in files:
        path, relative = _relative_file(item, base)
        size, digest = _sha256(path, base)
        entries.append({"path": relative, "size": size, "sha256": digest})
    entries.sort(key=lambda entry: entry["path"])
    return {"algorithm": "sha256", "files": entries}


def write_manifest(files: Iterable[str | Path], output: str | Path, *, base_dir: str | Path) -> dict:
    manifest = create_manifest(files, base_dir=base_dir)
    Path(output).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(manifest_path: str | Path, *, base_dir: str | Path) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("algorithm") != "sha256" or not isinstance(manifest.get("files"), list):
        raise ValueError("unsupported or invalid manifest")
    base = Path(base_dir).resolve(strict=True)
    changed, missing = [], []
    for entry in manifest["files"]:
        relative = entry["path"]
        candidate = Path(os.path.abspath(base / relative))
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"manifest path is outside base directory: {relative}") from exc
        try:
            _ensure_no_links(candidate, base)
        except FileNotFoundError:
            missing.append(relative)
            continue
        if not candidate.exists():
            missing.append(relative)
        else:
            size, digest = _sha256(candidate, base)
            if size != entry["size"] or digest != entry["sha256"]:
                changed.append(relative)
    return {"ok": not changed and not missing, "changed": sorted(changed), "missing": sorted(missing)}
