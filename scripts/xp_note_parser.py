"""Deterministic, local parser for XP brokerage notes.

The module deliberately separates PDF extraction from interpretation so the
financial rules can be tested without storing real customer documents.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence


MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGES = 20
MONEY_TOLERANCE = Decimal("0.02")


class NoteParseError(ValueError):
    """Raised when a note cannot be interpreted or reconciled safely."""


def _normalized(value: object) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )


def _decimal_br(value: object) -> Decimal:
    raw = str(value or "").strip().replace("R$", "").replace(" ", "")
    raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise NoteParseError(f"valor numérico inválido: {value!r}") from exc


def _integer_br(value: object) -> int:
    number = _decimal_br(value)
    if number != number.to_integral_value() or number <= 0:
        raise NoteParseError(f"quantidade inválida: {value!r}")
    return int(number)


def _header(text: str) -> dict[str, str]:
    compact = " ".join(text.split())
    match = re.search(
        r"nr\.?\s*nota\s+folha\s+data\s+preg[aã]o\s+"
        r"(?P<note>\d+)\s+\d+\s+(?P<date>\d{2}/\d{2}/\d{4})",
        compact,
        flags=re.IGNORECASE,
    )
    if not match:
        raise NoteParseError("cabeçalho da nota XP não identificado")
    day, month, year = match.group("date").split("/")
    return {
        "corretora": "XP INVESTIMENTOS",
        "numero_nota": match.group("note"),
        "data_pregao": f"{year}-{month}-{day}",
        "cliente": None,
        "codigo_cliente": None,
    }


def _column_indexes(header: Sequence[object]) -> dict[str, int] | None:
    normalized = [_normalized(cell) for cell in header]

    def find(*terms: str) -> int | None:
        for index, cell in enumerate(normalized):
            if any(term in cell for term in terms):
                return index
        return None

    indexes = {
        "negociacao": find("negociacao"),
        "side": find("c/v"),
        "market": find("tipo mercado"),
        "description": find("especificacao do titulo", "especificacao"),
        "observations": find("obs"),
        "quantity": find("quantidade"),
        "price": find("preco / ajuste", "preco/ajuste", "preco"),
        "total": find("valor operacao"),
        "dc": find("d/c"),
    }
    required = ("side", "description", "quantity", "price", "total")
    return indexes if all(indexes[key] is not None for key in required) else None


def _cell(row: Sequence[object], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return " ".join(str(row[index] or "").replace("\n", " ").split()).strip()


def _operation(row: Sequence[object], indexes: dict[str, int]) -> dict:
    side = _cell(row, indexes["side"]).upper()
    if side not in {"C", "V"}:
        raise NoteParseError(f"tipo de operação inválido: {side!r}")

    quantity = _integer_br(_cell(row, indexes["quantity"]))
    price = _decimal_br(_cell(row, indexes["price"]))
    total = _decimal_br(_cell(row, indexes["total"]))
    expected = price * quantity
    if abs(expected - total) > MONEY_TOLERANCE:
        raise NoteParseError(
            f"operação não reconcilia: quantidade × preço={expected} e total={total}"
        )

    negotiation = _cell(row, indexes["negociacao"])
    if not negotiation and row:
        negotiation = _cell(row, 0)

    return {
        "negociacao": negotiation,
        "tipo_operacao": "COMPRA" if side == "C" else "VENDA",
        "tipo_mercado": _cell(row, indexes["market"]),
        "descricao_ativo": _cell(row, indexes["description"]),
        "ticker": None,
        "observacoes": _cell(row, indexes["observations"]),
        "quantidade": quantity,
        "preco_unitario": price,
        "valor_operacao": total,
        "debito_credito": _cell(row, indexes["dc"]).upper(),
    }


def _operations(tables: Iterable[Sequence[Sequence[object]]]) -> list[dict]:
    operations: list[dict] = []
    for table in tables:
        indexes = None
        for row in table:
            if not row:
                continue
            candidate = _column_indexes(row)
            if candidate:
                indexes = candidate
                continue
            if indexes is None or not _cell(row, indexes["side"]):
                continue
            operations.append(_operation(row, indexes))
    if not operations:
        raise NoteParseError("nenhuma das operações foi reconhecida na nota")
    return operations


def parse_xp_document(text: str, tables: Iterable[Sequence[Sequence[object]]]) -> dict:
    """Parse already-extracted XP text/tables into the existing import contract."""
    return {
        "success": True,
        "header": _header(text),
        "financeiro": {},
        "operacoes_brutas": _operations(tables),
        "raw_text_preview": "",
    }


def parse_xp_pdf(pdf_path: Path, password: str | None = None) -> dict:
    """Extract and parse a local PDF without transmitting it to third parties."""
    if pdf_path.suffix.lower() != ".pdf":
        raise NoteParseError("somente arquivos PDF são aceitos")
    size = pdf_path.stat().st_size
    if size <= 0 or size > MAX_PDF_BYTES:
        raise NoteParseError("tamanho de PDF inválido")

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber não está instalado") from exc

    texts: list[str] = []
    tables: list[Sequence[Sequence[object]]] = []
    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            if not pdf.pages or len(pdf.pages) > MAX_PAGES:
                raise NoteParseError("quantidade de páginas inválida")
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
                tables.extend(page.extract_tables() or [])
    except NoteParseError:
        raise
    except Exception as exc:
        raise NoteParseError("não foi possível abrir ou extrair a nota") from exc

    return parse_xp_document("\n".join(texts), tables)
