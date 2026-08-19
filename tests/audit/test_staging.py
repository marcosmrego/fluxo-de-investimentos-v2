import pytest

from investment_audit.importers.staging import InvalidTransition, StagingRecord, StagingState


def test_happy_path_transitions_are_explicit():
    record = StagingRecord("idem-1")
    for state in (StagingState.ACQUIRED, StagingState.HASHED, StagingState.PARSED, StagingState.APPROVED, StagingState.PUBLISHED):
        record = record.transition_to(state)
    assert record.state is StagingState.PUBLISHED


def test_review_and_rejection_paths():
    parsed = StagingRecord("idem-1").transition_to(StagingState.ACQUIRED).transition_to(StagingState.HASHED).transition_to(StagingState.PARSED)
    assert parsed.transition_to(StagingState.NEEDS_REVIEW).transition_to(StagingState.APPROVED).state is StagingState.APPROVED
    assert parsed.transition_to(StagingState.REJECTED).state is StagingState.REJECTED


@pytest.mark.parametrize("start,target", [
    (StagingState.DISCOVERED, StagingState.PARSED),
    (StagingState.ACQUIRED, StagingState.APPROVED),
    (StagingState.PUBLISHED, StagingState.REJECTED),
    (StagingState.REJECTED, StagingState.DISCOVERED),
])
def test_invalid_transitions_fail_closed(start, target):
    with pytest.raises(InvalidTransition):
        StagingRecord("idem-1", start).transition_to(target)


def test_staging_identifier_is_required_and_safe():
    with pytest.raises(ValueError):
        StagingRecord("")
    with pytest.raises(ValueError):
        StagingRecord("../escape")
