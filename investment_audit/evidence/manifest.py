"""Deterministic, content-addressed evidence manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import re


_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,126}$")
_CONTENT_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,126}/[A-Za-z0-9][A-Za-z0-9._+-]{0,126}$")


class ValidationError(ValueError):
    """Raised when evidence metadata is not safe and canonical."""


def sha256_hex(value: bytes) -> str:
    return sha256(value).hexdigest()


def _require_hash(value: str, name: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValidationError(f"{name} must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_type: str
    source_id: str
    acquired_at: str
    content_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, str) or _TOKEN.fullmatch(self.source_type) is None:
            raise ValidationError("invalid source_type")
        if not isinstance(self.source_id, str) or _SAFE_SOURCE_ID.fullmatch(self.source_id) is None:
            raise ValidationError("invalid source_id")
        if not isinstance(self.content_type, str) or _CONTENT_TYPE.fullmatch(self.content_type) is None:
            raise ValidationError("invalid content_type")
        try:
            parsed = datetime.fromisoformat(self.acquired_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValidationError("acquired_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            raise ValidationError("acquired_at must include a timezone")


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    source: SourceMetadata
    plaintext_sha256: str
    ciphertext_sha256: str
    ciphertext_size: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.source, SourceMetadata):
            raise ValidationError("source must be validated SourceMetadata")
        _require_hash(self.plaintext_sha256, "plaintext_sha256")
        _require_hash(self.ciphertext_sha256, "ciphertext_sha256")
        if not isinstance(self.ciphertext_size, int) or isinstance(self.ciphertext_size, bool) or self.ciphertext_size < 0:
            raise ValidationError("ciphertext_size must be a non-negative integer")
        if self.schema_version != 1:
            raise ValidationError("unsupported schema_version")

    @classmethod
    def create(cls, source: SourceMetadata, plaintext_sha256: str, ciphertext_sha256: str, ciphertext_size: int) -> "EvidenceManifest":
        return cls(source, plaintext_sha256, ciphertext_sha256, ciphertext_size)

    def canonical_bytes(self) -> bytes:
        payload = {
            "ciphertext_sha256": self.ciphertext_sha256,
            "ciphertext_size": self.ciphertext_size,
            "plaintext_sha256": self.plaintext_sha256,
            "schema_version": self.schema_version,
            "source": asdict(self.source),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @property
    def manifest_sha256(self) -> str:
        return sha256_hex(self.canonical_bytes())

    @property
    def idempotency_id(self) -> str:
        identity = json.dumps(
            {"plaintext_sha256": self.plaintext_sha256, "source": asdict(self.source)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256_hex(identity)
