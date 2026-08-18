"""Pure domain rules for the portfolio investment-memory inventory."""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable


class ThesisOrigin(str, Enum):
    """How much historical certainty exists for a position thesis."""

    CONTEMPORARY = "TESE_CONTEMPORANEA"
    RECONSTRUCTED_CURRENT = "TESE_ATUAL_RECONSTRUIDA"
    UNKNOWN = "ORIGEM_DESCONHECIDA"


def _ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    return ticker


def _index_theses(theses: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    valid_origins = {origin.value for origin in ThesisOrigin}

    for raw_thesis in theses:
        thesis = dict(raw_thesis)
        ticker = _ticker(thesis.get("ticker"))
        if ticker in indexed:
            raise ValueError(f"duplicate thesis for {ticker}")

        origin = thesis.get("origin")
        if origin not in valid_origins:
            raise ValueError(f"invalid thesis origin for {ticker}")
        if origin == ThesisOrigin.CONTEMPORARY.value and not thesis.get("decision_at"):
            raise ValueError(f"decision_at is required for contemporary thesis {ticker}")

        thesis["ticker"] = ticker
        indexed[ticker] = thesis

    return indexed


def build_investment_inventory(
    positions: Iterable[dict[str, Any]],
    theses: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build a complete, explicit inventory without inventing historical intent."""

    indexed_theses = _index_theses(theses)
    inventory = []

    for raw_position in positions:
        quantity = float(raw_position.get("quantity") or 0)
        if quantity <= 0:
            continue

        ticker = _ticker(raw_position.get("ticker"))
        thesis = indexed_theses.get(ticker)
        origin = thesis["origin"] if thesis else ThesisOrigin.UNKNOWN.value
        item = {
            **raw_position,
            "ticker": ticker,
            "thesis_origin": origin,
            "thesis_summary": thesis.get("summary") if thesis else None,
            "thesis_recorded_at": thesis.get("recorded_at") if thesis else None,
            "decision_at": thesis.get("decision_at") if thesis else None,
            "is_original_decision_memory": origin == ThesisOrigin.CONTEMPORARY.value,
            "has_complete_thesis": bool(thesis and thesis.get("summary")),
        }
        inventory.append(item)

    inventory.sort(key=lambda item: item["ticker"])
    open_positions = len(inventory)
    complete_theses = sum(item["has_complete_thesis"] for item in inventory)
    explicit_gaps = open_positions - complete_theses

    return {
        "positions": inventory,
        "coverage": {
            "open_positions": open_positions,
            "inventoried_positions": open_positions,
            "complete_theses": complete_theses,
            "explicit_gaps": explicit_gaps,
            "coverage_pct": 100.0 if open_positions else 0.0,
            "complete_theses_pct": round(
                complete_theses / open_positions * 100, 1
            ) if open_positions else 0.0,
        },
    }
