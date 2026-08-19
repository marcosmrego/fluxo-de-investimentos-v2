"""Filesystem storage contract for objects encrypted by a trusted boundary."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Protocol


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class HashAttestationVerifier(Protocol):
    """Trusted crypto boundary; implementations may decrypt and attest hashes."""

    def verify_hashes(self, ciphertext: bytes, ciphertext_sha256: str, plaintext_sha256: str) -> bool: ...


class EvidenceIntegrityError(ValueError):
    """Raised when an encrypted object cannot be verified or safely placed."""


class FilesystemEncryptedObjectStore:
    """Atomically stores already-encrypted bytes; manages no keys.

    The configured root must be exclusively writable by this process's trust
    domain. Descriptor and entry-identity checks detect swaps during reads, but
    no portable pathname API can protect a root controlled by an attacker.
    """

    def __init__(self, root: Path | str, verifier: HashAttestationVerifier) -> None:
        configured_root = Path(root)
        self._verifier = verifier
        configured_root.mkdir(parents=True, exist_ok=True)
        self._root = configured_root.resolve(strict=True)

    def path_for(self, object_id: str) -> Path:
        if not isinstance(object_id, str) or _SAFE_ID.fullmatch(object_id) is None:
            raise ValueError("invalid object identifier")
        return self._root / f"{object_id}.enc"

    @staticmethod
    def _existing_hash(target: Path) -> str | None:
        try:
            before = os.lstat(target)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(before.st_mode):
            raise EvidenceIntegrityError("existing object target must be a regular file")

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags)
        except OSError as exc:
            raise EvidenceIntegrityError("existing object could not be safely opened") from exc
        digest = sha256()
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
                raise EvidenceIntegrityError("existing object changed while being verified")
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
        finally:
            os.close(descriptor)

        try:
            after = os.lstat(target)
        except FileNotFoundError as exc:
            raise EvidenceIntegrityError("existing object changed while being verified") from exc
        if not stat.S_ISREG(after.st_mode) or not os.path.samestat(opened, after):
            raise EvidenceIntegrityError("existing object changed while being verified")
        return digest.hexdigest()

    def put(self, object_id: str, ciphertext: bytes, ciphertext_sha256: str, plaintext_sha256: str) -> Path:
        target = self.path_for(object_id)
        if not isinstance(ciphertext, bytes) or not ciphertext:
            raise EvidenceIntegrityError("ciphertext must be non-empty bytes")
        if _HASH.fullmatch(ciphertext_sha256 or "") is None or _HASH.fullmatch(plaintext_sha256 or "") is None:
            raise EvidenceIntegrityError("invalid SHA-256 digest")
        actual_hash = sha256(ciphertext).hexdigest()
        if actual_hash != ciphertext_sha256:
            raise EvidenceIntegrityError("ciphertext hash mismatch")
        try:
            attested = self._verifier.verify_hashes(ciphertext, ciphertext_sha256, plaintext_sha256)
        except Exception as exc:
            raise EvidenceIntegrityError("hash attestation failed") from exc
        if attested is not True:
            raise EvidenceIntegrityError("hash attestation rejected")
        existing_hash = self._existing_hash(target)
        if existing_hash is not None:
            if existing_hash == ciphertext_sha256:
                return target
            raise EvidenceIntegrityError("object identifier collision")

        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self._root, prefix=f".{object_id}.", suffix=".tmp", delete=False) as handle:
                temp_name = handle.name
                handle.write(ciphertext)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, target)
            except FileExistsError:
                existing_hash = self._existing_hash(target)
                if existing_hash != ciphertext_sha256:
                    raise EvidenceIntegrityError("object identifier collision")
        finally:
            if temp_name is not None:
                Path(temp_name).unlink(missing_ok=True)
        return target
