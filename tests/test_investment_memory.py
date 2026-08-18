import pytest

from dashboard.investment_memory import (
    ThesisOrigin,
    build_investment_inventory,
)


def test_inventory_includes_every_open_position_and_marks_unknown_origins():
    positions = [
        {"ticker": "CMIN3", "quantity": 10, "market_value": 57.50},
        {"ticker": "VALE3", "quantity": 5, "market_value": 300.00},
        {"ticker": "CLOSED3", "quantity": 0, "market_value": 0},
    ]

    inventory = build_investment_inventory(positions, theses=[])

    assert [item["ticker"] for item in inventory["positions"]] == ["CMIN3", "VALE3"]
    assert all(
        item["thesis_origin"] == ThesisOrigin.UNKNOWN.value
        for item in inventory["positions"]
    )
    assert inventory["coverage"] == {
        "open_positions": 2,
        "inventoried_positions": 2,
        "complete_theses": 0,
        "explicit_gaps": 2,
        "coverage_pct": 100.0,
        "complete_theses_pct": 0.0,
    }


def test_inventory_distinguishes_contemporary_from_reconstructed_theses():
    positions = [
        {"ticker": "CMIN3", "quantity": 10, "market_value": 57.50},
        {"ticker": "VALE3", "quantity": 5, "market_value": 300.00},
    ]
    theses = [
        {
            "ticker": "CMIN3",
            "origin": ThesisOrigin.CONTEMPORARY.value,
            "summary": "Posicao inicial em mineracao.",
            "recorded_at": "2026-08-18T10:00:00-03:00",
            "decision_at": "2026-08-18T10:00:00-03:00",
        },
        {
            "ticker": "VALE3",
            "origin": ThesisOrigin.RECONSTRUCTED_CURRENT.value,
            "summary": "Tese atual registrada depois da compra.",
            "recorded_at": "2026-08-18T10:00:00-03:00",
            "decision_at": None,
        },
    ]

    inventory = build_investment_inventory(positions, theses)
    by_ticker = {item["ticker"]: item for item in inventory["positions"]}

    assert by_ticker["CMIN3"]["is_original_decision_memory"] is True
    assert by_ticker["VALE3"]["is_original_decision_memory"] is False
    assert inventory["coverage"]["complete_theses"] == 2
    assert inventory["coverage"]["explicit_gaps"] == 0


def test_contemporary_thesis_requires_decision_timestamp():
    positions = [{"ticker": "CMIN3", "quantity": 10, "market_value": 57.50}]
    theses = [{
        "ticker": "CMIN3",
        "origin": ThesisOrigin.CONTEMPORARY.value,
        "summary": "Compra inicial.",
        "recorded_at": "2026-08-18T10:00:00-03:00",
        "decision_at": None,
    }]

    with pytest.raises(ValueError, match="decision_at"):
        build_investment_inventory(positions, theses)


def test_inventory_rejects_duplicate_current_theses_for_the_same_ticker():
    positions = [{"ticker": "CMIN3", "quantity": 10, "market_value": 57.50}]
    thesis = {
        "ticker": "CMIN3",
        "origin": ThesisOrigin.RECONSTRUCTED_CURRENT.value,
        "summary": "Tese atual.",
        "recorded_at": "2026-08-18T10:00:00-03:00",
        "decision_at": None,
    }

    with pytest.raises(ValueError, match="duplicate thesis"):
        build_investment_inventory(positions, [thesis, thesis.copy()])


def test_inventory_rejects_unknown_thesis_origin_instead_of_guessing():
    positions = [{"ticker": "CMIN3", "quantity": 10, "market_value": 57.50}]
    theses = [{
        "ticker": "CMIN3",
        "origin": "ORIGINAL_PROVAVEL",
        "summary": "Classificacao ambigua.",
        "recorded_at": "2026-08-18T10:00:00-03:00",
        "decision_at": None,
    }]

    with pytest.raises(ValueError, match="invalid thesis origin"):
        build_investment_inventory(positions, theses)
