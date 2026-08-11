from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_overview_places_evolution_and_diversification_side_by_side():
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")

    start = html.index('id="chart-evolucao"')
    wrapper_start = html.rfind('<div class="charts-row overview-charts">', 0, start)
    wrapper_end = html.index("</div>", html.index('id="chart-donut"'))
    assert wrapper_start >= 0
    assert wrapper_end > start


def test_overview_evolution_is_annual_monthly_bar_chart():
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")

    assert "/api/rentabilidade?dias=365" in javascript
    assert "agruparFechamentosMensais" in javascript
    assert 'type: "bar"' in javascript


def test_overview_charts_stack_on_smaller_screens():
    css = (ROOT / "dashboard/static/style.css").read_text(encoding="utf-8")

    assert ".overview-charts" in css
    assert "grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr)" in css
