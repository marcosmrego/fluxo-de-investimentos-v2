import pytest

from dashboard.investment_memory import (
    ThesisOrigin,
    build_investment_inventory,
    create_initial_thesis_draft,
    validate_thesis_publication,
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
                "status": "PUBLICADA",
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
                "status": "PUBLICADA",
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


def test_contemporary_thesis_can_be_recorded_before_the_decision():
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

    inventory = build_investment_inventory(positions, theses)

    assert inventory["positions"][0]["is_original_decision_memory"] is True


def test_contemporary_thesis_cannot_be_recorded_more_than_24h_after_decision():
    positions = [{"ticker": "CMIN3", "quantity": 10, "market_value": 57.50}]
    theses = [{
        "ticker": "CMIN3",
        "origin": ThesisOrigin.CONTEMPORARY.value,
        "summary": "Compra inicial.",
        "recorded_at": "2026-08-19T10:00:01-03:00",
        "decision_at": "2026-08-18T10:00:00-03:00",
        "horizon": "2 a 4 anos",
        "risks": ["Minerio"],
        "review_triggers": ["Resultado trimestral"],
    }]

    with pytest.raises(ValueError, match="within 24 hours"):
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


def test_initial_draft_uses_only_position_classification_and_stays_incomplete():
    position = {
        "ticker": "BBAS3",
        "name": "Banco do Brasil",
        "asset_type": "ACAO",
        "sector": "Financeiro/Bancos",
    }

    thesis = create_initial_thesis_draft(
        position, recorded_at="2026-08-18T12:00:00-03:00"
    )
    inventory = build_investment_inventory(
        [{"ticker": "BBAS3", "quantity": 100, "market_value": 2500}],
        [thesis],
    )

    assert thesis["origin"] == ThesisOrigin.UNKNOWN.value
    assert thesis["status"] == "RASCUNHO"
    assert "Financeiro/Bancos" in thesis["summary"]
    assert thesis["risks"]
    assert thesis["review_triggers"]
    assert inventory["coverage"]["complete_theses"] == 0


def test_unknown_draft_does_not_require_or_claim_a_recorded_thesis_timestamp():
    thesis = create_initial_thesis_draft(
        {"ticker": "VALE3", "asset_type": "ACAO", "sector": "Mineracao"},
        recorded_at=None,
    )

    inventory = build_investment_inventory(
        [{"ticker": "VALE3", "quantity": 6, "market_value": 350}], [thesis]
    )

    assert inventory["positions"][0]["thesis_origin"] == "ORIGEM_DESCONHECIDA"
    assert inventory["positions"][0]["thesis_recorded_at"] is None
    assert inventory["positions"][0]["is_original_decision_memory"] is False


def test_reconstructed_thesis_publication_requires_complete_human_review():
    result = validate_thesis_publication({
        "origin": ThesisOrigin.RECONSTRUCTED_CURRENT.value,
        "summary": "Banco rentavel usado como exposicao financeira da carteira.",
        "horizon": "5 anos ou mais",
        "risks": ["Deterioracao de credito", "Interferencia politica"],
        "review_triggers": ["ROE abaixo do limite definido"],
    })

    assert result["status"] == "PUBLICADA"
    assert result["origin"] == ThesisOrigin.RECONSTRUCTED_CURRENT.value


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", "curta"),
        ("horizon", " "),
        ("risks", []),
        ("risks", [" "]),
        ("review_triggers", []),
    ],
)
def test_thesis_publication_rejects_incomplete_fields(field, value):
    payload = {
        "origin": ThesisOrigin.RECONSTRUCTED_CURRENT.value,
        "summary": "Tese revisada manualmente com contexto suficiente para acompanhamento.",
        "horizon": "longo prazo",
        "risks": ["Risco material revisado"],
        "review_triggers": ["Mudanca material dos fundamentos"],
    }
    payload[field] = value

    with pytest.raises(ValueError, match=field):
        validate_thesis_publication(payload)


def test_contemporary_publication_requires_decision_timestamp():
    payload = {
        "origin": ThesisOrigin.CONTEMPORARY.value,
        "summary": "Tese contemporanea revisada no momento da nova decisao de aporte.",
        "horizon": "2 a 4 anos",
        "risks": ["Risco de commodity"],
        "review_triggers": ["Resultado trimestral"],
        "decision_at": None,
    }

    with pytest.raises(ValueError, match="decision_at"):
        validate_thesis_publication(payload)


def test_contemporary_publication_rejects_decision_more_than_24h_in_future():
    payload = {
        "origin": ThesisOrigin.CONTEMPORARY.value,
        "summary": "Tese contemporanea revisada para uma decisao real de investimento.",
        "horizon": "2 a 4 anos",
        "risks": ["Risco material"],
        "review_triggers": ["Resultado trimestral"],
        "decision_at": "2026-08-20T12:00:01-03:00",
    }

    with pytest.raises(ValueError, match="24 hours"):
        validate_thesis_publication(
            payload, recorded_at="2026-08-19T12:00:00-03:00"
        )
