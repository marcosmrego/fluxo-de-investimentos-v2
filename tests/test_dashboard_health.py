from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_exposes_portfolio_health_section():
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")

    assert 'id="health-score"' in html
    assert 'id="health-pillars"' in html
    assert "/api/saude-carteira" in javascript
    assert "Confiabilidade:" in javascript
