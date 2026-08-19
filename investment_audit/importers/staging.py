"""Fail-closed state machine for evidence ingestion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import re


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")


class StagingState(str, Enum):
    DISCOVERED = "DISCOVERED"
    ACQUIRED = "ACQUIRED"
    HASHED = "HASHED"
    PARSED = "PARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


_TRANSITIONS = {
    StagingState.DISCOVERED: frozenset({StagingState.ACQUIRED, StagingState.REJECTED}),
    StagingState.ACQUIRED: frozenset({StagingState.HASHED, StagingState.REJECTED}),
    StagingState.HASHED: frozenset({StagingState.PARSED, StagingState.REJECTED}),
    StagingState.PARSED: frozenset({StagingState.NEEDS_REVIEW, StagingState.APPROVED, StagingState.REJECTED}),
    StagingState.NEEDS_REVIEW: frozenset({StagingState.APPROVED, StagingState.REJECTED}),
    StagingState.APPROVED: frozenset({StagingState.PUBLISHED, StagingState.REJECTED}),
    StagingState.PUBLISHED: frozenset(),
    StagingState.REJECTED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when a staging state transition is not explicitly allowed."""


@dataclass(frozen=True, slots=True)
class StagingRecord:
    idempotency_id: str
    state: StagingState = StagingState.DISCOVERED

    def __post_init__(self) -> None:
        if not isinstance(self.idempotency_id, str) or _SAFE_ID.fullmatch(self.idempotency_id) is None:
            raise ValueError("invalid idempotency identifier")
        if not isinstance(self.state, StagingState):
            raise ValueError("invalid staging state")

    def transition_to(self, target: StagingState) -> "StagingRecord":
        if not isinstance(target, StagingState) or target not in _TRANSITIONS[self.state]:
            raise InvalidTransition(f"transition {self.state.value} -> {getattr(target, 'value', target)!s} is not allowed")
        return replace(self, state=target)
