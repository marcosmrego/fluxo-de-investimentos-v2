from dashboard.portfolio_health import compute_portfolio_health


def test_balanced_portfolio_scores_better_than_concentrated_one():
    balanced = [
        {"ticker": f"A{i}", "sector": f"S{i % 5}", "value": 100, "has_quote": True, "registered": True}
        for i in range(10)
    ]
    concentrated = [
        {"ticker": "BIG", "sector": "Banco", "value": 800, "has_quote": True, "registered": True},
        {"ticker": "SMALL", "sector": "Energia", "value": 200, "has_quote": True, "registered": True},
    ]

    assert compute_portfolio_health(balanced)["score"] > compute_portfolio_health(concentrated)["score"]


def test_missing_quotes_reduce_confidence_and_create_alert():
    result = compute_portfolio_health([
        {"ticker": "OK", "sector": "Banco", "value": 100, "has_quote": True, "registered": True},
        {"ticker": "MISS", "sector": "Energia", "value": 50, "has_quote": False, "registered": True},
    ])

    assert result["confidence"] == "baixa"
    assert any("cobertura" in alert["text"].lower() for alert in result["alerts"])


def test_empty_portfolio_is_explicitly_unavailable():
    result = compute_portfolio_health([])
    assert result["score"] is None
    assert result["classification"] == "Indisponivel"


def test_cumulative_history_is_converted_to_period_returns():
    positions = [
        {"ticker": f"A{i}", "sector": f"S{i}", "value": 100, "has_quote": True, "registered": True}
        for i in range(10)
    ]
    result = compute_portfolio_health(positions, [1.0] * 25)

    assert result["metrics"]["annualized_volatility_pct"] == 0.0
    assert result["metrics"]["max_drawdown_pct"] == 0.0


def test_summary_names_the_actual_weakest_pillar():
    positions = [
        {"ticker": f"A{i}", "sector": f"S{i}", "value": 100, "has_quote": i > 4, "registered": i > 4}
        for i in range(10)
    ]
    result = compute_portfolio_health(positions)

    assert "qualidade dos dados" in result["summary"].lower()
