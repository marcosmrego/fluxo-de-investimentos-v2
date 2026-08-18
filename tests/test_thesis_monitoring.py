from dashboard.thesis_monitoring import evaluate_thesis_monitoring


def test_first_monitoring_run_creates_baseline_without_alert():
    result = evaluate_thesis_monitoring(None, {"price": 10, "data_age_days": 1}, "ACAO", 0)

    assert result["status"] == "BASELINE_CRIADO"
    assert result["triggers"] == []


def test_stale_data_has_priority_over_market_movements():
    result = evaluate_thesis_monitoring(
        {"price": 10}, {"price": 20, "data_age_days": 31}, "ACAO", 10
    )

    assert result["status"] == "DADOS_INSUFICIENTES"
    assert "dados_desatualizados" in result["triggers"]


def test_material_price_and_roe_changes_recommend_review():
    result = evaluate_thesis_monitoring(
        {"price": 10, "roe": 16},
        {"price": 12, "roe": 12.5, "data_age_days": 1},
        "ACAO",
        20,
    )

    assert result["status"] == "REVISAO_RECOMENDADA"
    assert "preco_desde_tese" in result["triggers"]
    assert "mudanca_roe" in result["triggers"]


def test_periodic_review_depends_on_asset_class():
    fii = evaluate_thesis_monitoring(
        {"price": 100}, {"price": 101, "data_age_days": 1}, "FII", 31
    )
    stock = evaluate_thesis_monitoring(
        {"price": 100}, {"price": 101, "data_age_days": 1}, "ACAO", 31
    )

    assert fii["status"] == "REVISAO_RECOMENDADA"
    assert "revisao_periodica" in fii["triggers"]
    assert stock["status"] == "SEM_MUDANCA_MATERIAL"


def test_small_changes_are_recorded_without_creating_noise():
    result = evaluate_thesis_monitoring(
        {"price": 10, "p_l": 8},
        {"price": 10.2, "p_l": 8.5, "data_age_days": 1},
        "ACAO",
        10,
    )

    assert result["status"] == "SEM_MUDANCA_MATERIAL"
    assert result["triggers"] == []
