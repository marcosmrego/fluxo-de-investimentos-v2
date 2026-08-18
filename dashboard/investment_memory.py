"""Pure domain rules for the portfolio investment-memory inventory."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
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


def _aware_datetime(value: Any, field: str, ticker: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid timezone-aware timestamp for {ticker}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be a valid timezone-aware timestamp for {ticker}")
    return parsed


def _positive_quantity(value: Any, ticker: str) -> Decimal:
    try:
        quantity = Decimal(str(value or 0))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid quantity for {ticker}") from exc
    if not quantity.is_finite():
        raise ValueError(f"invalid quantity for {ticker}")
    return quantity


def _is_complete_thesis(thesis: dict[str, Any] | None) -> bool:
    if not thesis or thesis.get("origin") == ThesisOrigin.UNKNOWN.value:
        return False
    return all((
        bool(str(thesis.get("summary") or "").strip()),
        bool(str(thesis.get("horizon") or "").strip()),
        bool(thesis.get("risks")),
        bool(thesis.get("review_triggers")),
        bool(thesis.get("recorded_at")),
    ))


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
        recorded_at = _aware_datetime(thesis.get("recorded_at"), "recorded_at", ticker)
        if origin == ThesisOrigin.CONTEMPORARY.value and not thesis.get("decision_at"):
            raise ValueError(f"decision_at is required for contemporary thesis {ticker}")
        if origin == ThesisOrigin.CONTEMPORARY.value:
            decision_at = _aware_datetime(thesis["decision_at"], "decision_at", ticker)
            if recorded_at < decision_at:
                raise ValueError(f"recorded_at cannot be before decision_at for {ticker}")

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
    seen_positions: set[str] = set()

    for raw_position in positions:
        ticker = _ticker(raw_position.get("ticker"))
        quantity = _positive_quantity(raw_position.get("quantity"), ticker)
        if quantity <= 0:
            continue

        if ticker in seen_positions:
            raise ValueError(f"duplicate open position for {ticker}")
        seen_positions.add(ticker)
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
            "has_complete_thesis": _is_complete_thesis(thesis),
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
