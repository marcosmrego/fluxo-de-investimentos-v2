from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_has_theses_and_decisions_tab():
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")

    assert 'data-tab="teses"' in html
    assert 'id="tab-teses"' in html
    assert "Teses e decisoes" in html


def test_theses_tab_loads_real_inventory_endpoint_and_renders_coverage():
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")

    assert 'case "teses": carregarTeses(); break;' in javascript
    assert "/api/teses/inventario" in javascript
    assert 'document.getElementById("thesis-coverage")' in javascript
