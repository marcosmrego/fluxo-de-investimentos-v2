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
