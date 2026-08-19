from decimal import Decimal
from pathlib import Path
import sys

import pytest

from scripts.xp_note_parser import NoteParseError, parse_xp_document

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


HEADER_TEXT = """
NOTA DE NEGOCIAÇÃO
Nr. nota Folha Data pregão
987654 1 10/08/2026
"""

OPERATIONS_TABLE = [
    [
        "Q", "Negociação", "C/V", "Tipo mercado", "Prazo",
        "Especificação do título", "Obs.", "Quantidade",
        "Preço / Ajuste", "Valor Operação", "D/C",
    ],
    [
        "1-BOVESPA", "", "C", "VISTA", "", "KLABIN S/A UNT N2",
        "", "100", "18,31", "1.831,00", "D",
    ],
    [
        "1-BOVESPA", "", "V", "VISTA", "", "FII LOGISTICA CI ER",
        "", "5", "160,00", "800,00", "C",
    ],
]


def test_parses_anonymized_xp_header_and_operations():
    result = parse_xp_document(HEADER_TEXT, [OPERATIONS_TABLE])

    assert result["header"]["numero_nota"] == "987654"
    assert result["header"]["data_pregao"] == "2026-08-10"
    assert result["operacoes_brutas"] == [
        {
            "negociacao": "1-BOVESPA",
            "tipo_operacao": "COMPRA",
            "tipo_mercado": "VISTA",
            "descricao_ativo": "KLABIN S/A UNT N2",
            "ticker": None,
            "observacoes": "",
            "quantidade": 100,
            "preco_unitario": Decimal("18.31"),
            "valor_operacao": Decimal("1831.00"),
            "debito_credito": "D",
        },
        {
            "negociacao": "1-BOVESPA",
            "tipo_operacao": "VENDA",
            "tipo_mercado": "VISTA",
            "descricao_ativo": "FII LOGISTICA CI ER",
            "ticker": None,
            "observacoes": "",
            "quantidade": 5,
            "preco_unitario": Decimal("160.00"),
            "valor_operacao": Decimal("800.00"),
            "debito_credito": "C",
        },
    ]


def test_rejects_operation_whose_total_does_not_reconcile():
    invalid = [OPERATIONS_TABLE[0], OPERATIONS_TABLE[1][:-2] + ["1.900,00", "D"]]

    with pytest.raises(NoteParseError, match="não reconcilia"):
        parse_xp_document(HEADER_TEXT, [invalid])


def test_rejects_document_without_note_identity():
    with pytest.raises(NoteParseError, match="cabeçalho"):
        parse_xp_document("documento sem identificação", [OPERATIONS_TABLE])


def test_rejects_document_without_operations():
    with pytest.raises(NoteParseError, match="operações"):
        parse_xp_document(HEADER_TEXT, [])


def test_accepts_brazilian_numbers_with_thousands_and_decimal_comma():
    result = parse_xp_document(HEADER_TEXT, [OPERATIONS_TABLE])

    operation = result["operacoes_brutas"][0]
    assert operation["preco_unitario"] == Decimal("18.31")
    assert operation["valor_operacao"] == Decimal("1831.00")


def test_parses_xp_table_when_pdf_omits_the_header_row():
    extracted_without_header = [OPERATIONS_TABLE[1]]

    result = parse_xp_document(HEADER_TEXT, [extracted_without_header])

    assert len(result["operacoes_brutas"]) == 1
    assert result["operacoes_brutas"][0]["tipo_operacao"] == "COMPRA"


def test_processador_uses_local_parser(monkeypatch, tmp_path):
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    import processar_nota_xp

    expected = {"success": True, "header": {"numero_nota": "987654"}}
    note = tmp_path / "nota.pdf"
    note.write_bytes(b"%PDF-test")
    called = {}

    def fake_local_parser(path, password=None):
        called.update(path=path, password=password)
        return expected

    monkeypatch.setattr(processar_nota_xp, "parse_xp_pdf", fake_local_parser, raising=False)

    assert processar_nota_xp.parse_pdf(note, "senha-segura") == expected
    assert called == {"path": note, "password": "senha-segura"}


def test_gmail_importer_has_no_hardcoded_note_password():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "scripts" / "buscar_notas_gmail.py").read_text(
        encoding="utf-8"
    )
    assert 'XP_SENHA = "822"' not in source
    assert 'os.environ.get("XP_NOTAS_PASSWORD")' in source
    assert "load_dotenv" in source


def test_unresolved_ticker_blocks_database_write():
    import processar_nota_xp

    with pytest.raises(ValueError, match="ticker não resolvido"):
        processar_nota_xp.validar_operacoes_para_gravacao(
            [{"ticker": None, "descricao_ativo": "ATIVO DESCONHECIDO"}]
        )


@pytest.mark.parametrize(
    "description,ticker",
    [
        ("SPACE X DRN", "SPCX34"),
        ("NU HOLDINGS DRN", "ROXO34"),
        ("BTG S&P 500 CI", "SPXB11"),
    ],
)
def test_resolves_verified_b3_descriptions(description, ticker):
    import processar_nota_xp

    assert processar_nota_xp.ticker_oficial_por_descricao(description) == ticker


def test_verified_tickers_have_asset_metadata():
    import processar_nota_xp

    assert processar_nota_xp.ATIVOS_B3_VERIFICADOS["SPCX34"]["tipo"] == "BDR"
    assert processar_nota_xp.ATIVOS_B3_VERIFICADOS["ROXO34"]["tipo"] == "BDR"


def test_asset_registration_precedes_note_write(monkeypatch, tmp_path):
    import processar_nota_xp

    note = tmp_path / "nota.pdf"
    note.write_bytes(b"%PDF-test")
    parsed = {
        "header": {"numero_nota": "987654"},
        "financeiro": {},
        "operacoes_brutas": [{
            "ticker": "SPCX34",
            "descricao_ativo": "SPACE X DRN",
            "tipo_operacao": "COMPRA",
            "quantidade": 2,
            "preco_unitario": Decimal("45.41"),
            "valor_operacao": Decimal("90.82"),
        }],
    }
    events = []

    class Connection:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    monkeypatch.setattr(processar_nota_xp, "parse_pdf", lambda *_: parsed)
    monkeypatch.setattr(processar_nota_xp, "resolver_tickers", lambda ops, conn: ops)
    monkeypatch.setattr(processar_nota_xp, "nota_ja_processada", lambda *_: False)
    monkeypatch.setattr(processar_nota_xp, "garantir_cadastros_ativos", lambda *_: events.append("ativos"))
    monkeypatch.setattr(processar_nota_xp, "inserir_nota", lambda *_args, **_kwargs: events.append("nota") or "id")
    monkeypatch.setattr(processar_nota_xp, "inserir_operacoes", lambda *_: None)
    monkeypatch.setattr(processar_nota_xp, "inserir_consolidadas", lambda *_: None)
    monkeypatch.setattr(processar_nota_xp, "atualizar_posicoes", lambda *_: events.append("posicoes"))

    assert processar_nota_xp.processar_pdf(note, Connection()) is True
    assert events == ["ativos", "nota", "posicoes", "commit"]


def test_import_failure_persists_email_error_in_new_transaction(monkeypatch, tmp_path):
    import processar_nota_xp

    note = tmp_path / "nota.pdf"
    note.write_bytes(b"%PDF-test")
    events = []

    class Connection:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    parsed = {"header": {"numero_nota": "987654"}, "operacoes_brutas": []}
    monkeypatch.setattr(processar_nota_xp, "parse_pdf", lambda *_: parsed)
    monkeypatch.setattr(processar_nota_xp, "resolver_tickers", lambda ops, conn: ops)
    monkeypatch.setattr(processar_nota_xp, "nota_ja_processada", lambda *_: False)
    monkeypatch.setattr(processar_nota_xp, "garantir_cadastros_ativos", lambda *_: None)
    monkeypatch.setattr(processar_nota_xp, "inserir_nota", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db failure")))
    monkeypatch.setattr(processar_nota_xp, "registrar_email_processado", lambda _conn, _email, _file, status, *_args, **_kwargs: events.append(status))

    with pytest.raises(RuntimeError, match="db failure"):
        processar_nota_xp.processar_pdf(note, Connection(), email_id="gmail-id")

    assert events == ["processando", "rollback", "erro", "commit"]


def test_parse_failure_is_recorded_without_replacing_original_error(monkeypatch, tmp_path):
    import processar_nota_xp

    note = tmp_path / "nota.pdf"
    note.write_bytes(b"%PDF-test")
    events = []

    class Connection:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    monkeypatch.setattr(processar_nota_xp, "parse_pdf", lambda *_: (_ for _ in ()).throw(ValueError("invalid pdf")))
    monkeypatch.setattr(processar_nota_xp, "registrar_email_processado", lambda *_args, **_kwargs: events.append("erro"))

    with pytest.raises(ValueError, match="invalid pdf"):
        processar_nota_xp.processar_pdf(note, Connection(), email_id="gmail-id")

    assert events == ["rollback", "erro", "commit"]


def test_duplicate_note_is_considered_handled_by_gmail_importer(monkeypatch, tmp_path):
    import buscar_notas_gmail

    note = tmp_path / "nota.pdf"
    note.write_bytes(b"%PDF-test")

    class Result:
        returncode = 0
        stdout = "[PULAR] Nota 987654 já existe no banco"
        stderr = ""

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Result()

    monkeypatch.setattr(buscar_notas_gmail.subprocess, "run", fake_run)
    monkeypatch.setattr(buscar_notas_gmail, "XP_SENHA", None)

    assert buscar_notas_gmail.processar_pdf(note, "gmail-message-id") is True
    assert None not in captured["command"]
    assert "--senha" not in captured["command"]
