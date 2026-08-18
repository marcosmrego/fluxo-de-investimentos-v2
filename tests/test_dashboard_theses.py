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


def test_theses_tab_has_review_dialog_and_publishes_versioned_thesis():
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")

    assert 'id="thesis-dialog"' in html
    assert 'id="thesis-form"' in html
    assert "/api/teses/${encodeURIComponent(ticker)}/publicar" in javascript
    assert 'method: "POST"' in javascript
    assert "resetarFormularioTese" in javascript


def test_review_dialog_prefills_automatic_explainable_proposal():
    javascript = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")

    assert "/api/teses/${encodeURIComponent(item.ticker)}/proposta" in javascript
    assert "proposal.confidence" in javascript
    assert 'document.getElementById("thesis-summary").value = proposal.summary' in javascript
