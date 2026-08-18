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
            "horizon": "2 a 4 anos",
            "risks": ["Queda do minerio"],
            "review_triggers": ["Resultado trimestral"],
        },
        {
            "ticker": "VALE3",
            "origin": ThesisOrigin.RECONSTRUCTED_CURRENT.value,
            "summary": "Tese atual registrada depois da compra.",
            "recorded_at": "2026-08-18T10:00:00-03:00",
            "decision_at": None,
            "horizon": "longo prazo",
            "risks": ["China"],
            "review_triggers": ["Mudanca da tese"],
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


@pytest.mark.parametrize("decision_at", ["ontem", "2026-08-18T10:00:00"])
def test_contemporary_thesis_requires_valid_timezone_aware_decision(decision_at):
    positions = [{"ticker": "CMIN3", "quantity": 10, "market_value": 57.50}]
    theses = [{
        "ticker": "CMIN3",
        "origin": ThesisOrigin.CONTEMPORARY.value,
        "summary": "Compra inicial.",
        "recorded_at": "2026-08-18T11:00:00-03:00",
        "decision_at": decision_at,
        "horizon": "2 a 4 anos",
        "risks": ["Minerio"],
        "review_triggers": ["Resultado trimestral"],
    }]

    with pytest.raises(ValueError, match="timezone-aware"):
        build_investment_inventory(positions, theses)


def test_contemporary_thesis_cannot_be_recorded_before_the_decision():
    positions = [{"ticker": "CMIN3", "quantity": 10, "market_value": 57.50}]
    theses = [{
        "ticker": "CMIN3",
        "origin": ThesisOrigin.CONTEMPORARY.value,
        "summary": "Compra inicial.",
        "recorded_at": "2026-08-18T09:00:00-03:00",
        "decision_at": "2026-08-18T10:00:00-03:00",
        "horizon": "2 a 4 anos",
        "risks": ["Minerio"],
        "review_triggers": ["Resultado trimestral"],
    }]

    with pytest.raises(ValueError, match="before decision_at"):
        build_investment_inventory(positions, theses)


def test_thesis_is_not_complete_when_minimum_decision_fields_are_missing():
    positions = [{"ticker": "VALE3", "quantity": 5, "market_value": 300.00}]
    theses = [{
        "ticker": "VALE3",
        "origin": ThesisOrigin.RECONSTRUCTED_CURRENT.value,
        "summary": "   ",
        "recorded_at": "2026-08-18T10:00:00-03:00",
        "decision_at": None,
        "horizon": None,
        "risks": [],
        "review_triggers": [],
    }]

    inventory = build_investment_inventory(positions, theses)

    assert inventory["positions"][0]["has_complete_thesis"] is False
    assert inventory["coverage"]["complete_theses"] == 0


@pytest.mark.parametrize("quantity", [float("nan"), float("inf"), "invalid"])
def test_inventory_rejects_invalid_position_quantities(quantity):
    positions = [{"ticker": "CMIN3", "quantity": quantity, "market_value": 57.50}]

    with pytest.raises(ValueError, match="invalid quantity"):
        build_investment_inventory(positions, theses=[])


def test_inventory_rejects_duplicate_open_positions_until_identity_is_canonical():
    positions = [
        {"ticker": "CMIN3", "quantity": 5, "market_value": 28.75},
        {"ticker": "CMIN3", "quantity": 5, "market_value": 28.75},
    ]

    with pytest.raises(ValueError, match="duplicate open position"):
        build_investment_inventory(positions, theses=[])
