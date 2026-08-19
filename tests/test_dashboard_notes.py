import importlib
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_main(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "investidor")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "segredo-de-teste")
    import dashboard.main as main
    return importlib.reload(main)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


def test_notes_contract_groups_statuses_and_omits_sensitive_data(monkeypatch):
    main = _load_main(monkeypatch)
    timestamp = datetime(2026, 8, 19, 13, 42, tzinfo=timezone.utc)
    notes = [
        {
            "id": "note-imported", "data_pregao": date(2026, 8, 18),
            "criado_em": timestamp, "corretora": "XP INVESTIMENTOS",
            "numero_nota": "123", "email_id": "email-1",
            "valor_liquido_operacoes": Decimal("100.25"),
            "total_custos_despesas": Decimal("1.50"),
            "liquido_para_valor": Decimal("98.75"),
            "operations": [{"ticker": "PETR4", "description": "PETROBRAS PN",
                            "side": "COMPRA", "market": "VISTA",
                            "quantity": Decimal("2"), "unit_price": Decimal("50.125"),
                            "total_value": Decimal("100.25")}],
        },
        {
            "id": "note-manual", "data_pregao": date(2026, 8, 17),
            "criado_em": timestamp, "corretora": "XP INVESTIMENTOS",
            "numero_nota": "122", "email_id": None,
            "valor_liquido_operacoes": None, "total_custos_despesas": None,
            "liquido_para_valor": None, "operations": [],
        },
    ]
    attempts = [
        {"id": "attempt-1", "status_processamento": "erro", "atualizado_em": timestamp},
        {"id": "attempt-2", "status_processamento": "processando", "atualizado_em": timestamp},
    ]

    class Connection:
        def execute(self, statement, _params=None):
            sql = str(statement)
            return _Rows(attempts if "emails_processados e" in sql else notes)

    class Context:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_):
            return False

    class Engine:
        def connect(self):
            return Context()

    monkeypatch.setattr(main, "engine", Engine())
    result = main.load_negotiation_notes()

    assert result["summary"] == {"total": 4, "imported": 1, "processing": 1, "error": 1, "manual": 1}
    assert result["limit_per_source"] == 100
    assert [group["date"] for group in result["groups"]] == ["2026-08-19", "2026-08-18", "2026-08-17"]
    items = [item for group in result["groups"] for item in group["items"]]
    assert {item["status"] for item in items} == {"Imported", "Manual", "Processing", "Error"}
    imported = next(item for item in items if item["status"] == "Imported")
    assert imported["operations"][0]["total_value"] == 100.25
    assert next(item for item in items if item["status"] == "Error")["status_message"] == "Não foi possível importar esta nota."
    serialized = repr(result).lower()
    for forbidden in ("cliente_nome", "codigo_cliente", "raw_text", "arquivo_nome", "message_id", "erro_processamento"):
        assert forbidden not in serialized


def test_notes_tab_is_lazy_loaded_and_has_all_status_styles():
    html = (ROOT / "dashboard/static/index.html").read_text(encoding="utf-8")
    js = (ROOT / "dashboard/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "dashboard/static/style.css").read_text(encoding="utf-8")

    assert 'data-tab="notas"' in html
    assert 'id="tab-notas"' in html
    assert 'aria-controls="tab-notas"' in html
    assert 'role="tabpanel" aria-labelledby="notes-tab"' in html
    assert "notas: false" in js
    assert 'case "notas": carregarNotas()' in js
    assert "/api/notas" in js
    for status in ("imported", "manual", "processing", "error"):
        assert f".note-status-{status}" in css
