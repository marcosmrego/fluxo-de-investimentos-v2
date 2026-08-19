import json

import pytest

from investment_audit.evidence.manifest import EvidenceManifest, SourceMetadata, ValidationError, sha256_hex


def test_manifest_is_deterministic_and_has_stable_idempotency_id():
    source = SourceMetadata("broker_statement", "xp:note:123", "2026-08-19T12:30:00Z", "application/pdf")
    first = EvidenceManifest.create(source, "a" * 64, "b" * 64, 42)
    second = EvidenceManifest.create(source, "a" * 64, "b" * 64, 42)
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.manifest_sha256 == sha256_hex(first.canonical_bytes())
    assert first.idempotency_id == second.idempotency_id
    assert json.loads(first.canonical_bytes())["source"]["source_id"] == "xp:note:123"


@pytest.mark.parametrize("kwargs", [
    {"source_type": "", "source_id": "id", "acquired_at": "2026-08-19T12:30:00Z", "content_type": "application/pdf"},
    {"source_type": "note", "source_id": "../escape", "acquired_at": "2026-08-19T12:30:00Z", "content_type": "application/pdf"},
    {"source_type": "note", "source_id": "id", "acquired_at": "yesterday", "content_type": "application/pdf"},
    {"source_type": "note", "source_id": "id", "acquired_at": "2026-08-19T12:30:00Z", "content_type": "text/plain\nsecret"},
])
def test_source_metadata_fails_closed(kwargs):
    with pytest.raises(ValidationError):
        SourceMetadata(**kwargs)


def test_manifest_rejects_bad_hashes_and_sizes():
    source = SourceMetadata("note", "id", "2026-08-19T12:30:00Z", "application/pdf")
    with pytest.raises(ValidationError):
        EvidenceManifest.create(source, "nope", "b" * 64, 1)
    with pytest.raises(ValidationError):
        EvidenceManifest.create(source, "a" * 64, "b" * 64, -1)


def test_direct_manifest_construction_cannot_bypass_validation():
    source = SourceMetadata("note", "id", "2026-08-19T12:30:00Z", "application/pdf")
    with pytest.raises(ValidationError):
        EvidenceManifest(source, "not-a-hash", "b" * 64, 1)


def test_manifest_keeps_plaintext_and_ciphertext_hashes_distinct():
    source = SourceMetadata("note", "id", "2026-08-19T12:30:00Z", "application/pdf")
    manifest = EvidenceManifest.create(source, "a" * 64, "b" * 64, 10)
    payload = json.loads(manifest.canonical_bytes())
    assert payload["plaintext_sha256"] == "a" * 64
    assert payload["ciphertext_sha256"] == "b" * 64
    assert payload["plaintext_sha256"] != payload["ciphertext_sha256"]
