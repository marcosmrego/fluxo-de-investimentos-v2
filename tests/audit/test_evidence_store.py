from hashlib import sha256
import os
import stat

import pytest

from investment_audit.evidence.store import EvidenceIntegrityError, FilesystemEncryptedObjectStore
import investment_audit.evidence.store as store_module


class TrustedVerifier:
    def __init__(self, accepted_plaintext_hash):
        self.accepted_plaintext_hash = accepted_plaintext_hash

    def verify_hashes(self, ciphertext, ciphertext_sha256, plaintext_sha256):
        return sha256(ciphertext).hexdigest() == ciphertext_sha256 and plaintext_sha256 == self.accepted_plaintext_hash


class RecordingVerifier(TrustedVerifier):
    def __init__(self, accepted_plaintext_hash):
        super().__init__(accepted_plaintext_hash)
        self.calls = []

    def verify_hashes(self, ciphertext, ciphertext_sha256, plaintext_sha256):
        self.calls.append((ciphertext_sha256, plaintext_sha256))
        return super().verify_hashes(ciphertext, ciphertext_sha256, plaintext_sha256)


def test_store_atomically_places_already_encrypted_bytes_and_is_idempotent(tmp_path):
    ciphertext = b"encrypted-object-not-pdf-content"
    cipher_hash, plain_hash = sha256(ciphertext).hexdigest(), "a" * 64
    store = FilesystemEncryptedObjectStore(tmp_path, TrustedVerifier(plain_hash))
    first = store.put("evidence-123", ciphertext, cipher_hash, plain_hash)
    second = store.put("evidence-123", ciphertext, cipher_hash, plain_hash)
    assert first == second
    assert first.read_bytes() == ciphertext
    assert not list(tmp_path.rglob("*.tmp"))


def test_store_fails_closed_on_untrusted_hashes_or_identifier(tmp_path):
    store = FilesystemEncryptedObjectStore(tmp_path, TrustedVerifier("a" * 64))
    with pytest.raises(EvidenceIntegrityError):
        store.put("id", b"ciphertext", "0" * 64, "a" * 64)
    with pytest.raises(ValueError):
        store.put("../escape", b"ciphertext", sha256(b"ciphertext").hexdigest(), "a" * 64)


def test_store_rejects_collision_without_overwriting(tmp_path):
    store = FilesystemEncryptedObjectStore(tmp_path, TrustedVerifier("a" * 64))
    original = b"encrypted-one"
    store.put("same-id", original, sha256(original).hexdigest(), "a" * 64)
    replacement = b"encrypted-two"
    with pytest.raises(EvidenceIntegrityError):
        store.put("same-id", replacement, sha256(replacement).hexdigest(), "a" * 64)
    assert store.path_for("same-id").read_bytes() == original


def test_ciphertext_is_verified_from_bytes_but_plaintext_requires_attestation(tmp_path):
    ciphertext = b"opaque-encrypted-object"
    ciphertext_hash = sha256(ciphertext).hexdigest()
    plaintext_hash = sha256(b"different-plaintext").hexdigest()
    verifier = RecordingVerifier(plaintext_hash)
    store = FilesystemEncryptedObjectStore(tmp_path, verifier)

    store.put("distinct-hashes", ciphertext, ciphertext_hash, plaintext_hash)

    assert ciphertext_hash != plaintext_hash
    assert verifier.calls == [(ciphertext_hash, plaintext_hash)]
    with pytest.raises(EvidenceIntegrityError):
        store.put("bad-attestation", ciphertext, ciphertext_hash, "f" * 64)


def test_store_rejects_existing_symlink_even_when_target_hash_matches(tmp_path, monkeypatch):
    ciphertext = b"opaque-encrypted-object"
    store = FilesystemEncryptedObjectStore(tmp_path / "store", TrustedVerifier("a" * 64))
    target = store.path_for("linked")
    target.write_bytes(ciphertext)
    original_lstat = os.lstat
    values = list(original_lstat(target))
    values[stat.ST_MODE] = stat.S_IFLNK | 0o777
    symlink_stat = os.stat_result(values)
    monkeypatch.setattr(store_module.os, "lstat", lambda path: symlink_stat if path == target else original_lstat(path))

    with pytest.raises(EvidenceIntegrityError):
        store.put("linked", ciphertext, sha256(ciphertext).hexdigest(), "a" * 64)


def test_store_rejects_existing_entry_swapped_while_hashing(tmp_path, monkeypatch):
    ciphertext = b"opaque-encrypted-object"
    store = FilesystemEncryptedObjectStore(tmp_path / "store", TrustedVerifier("a" * 64))
    target = store.path_for("raced")
    target.write_bytes(ciphertext)
    original_lstat = os.lstat
    original = original_lstat(target)
    changed_values = list(original)
    changed_values[stat.ST_INO] = original.st_ino + 1
    changed = os.stat_result(changed_values)
    calls = 0

    def swapped_lstat(path):
        nonlocal calls
        if path == target:
            calls += 1
            return original if calls == 1 else changed
        return original_lstat(path)

    monkeypatch.setattr(store_module.os, "lstat", swapped_lstat)
    with pytest.raises(EvidenceIntegrityError, match="changed while being verified"):
        store.put("raced", ciphertext, sha256(ciphertext).hexdigest(), "a" * 64)
