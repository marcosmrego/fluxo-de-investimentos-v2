"""Deterministic daily monitoring rules for published investment theses."""

from __future__ import annotations

import math
from typing import Any


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _relative_change(previous: Any, current: Any) -> float | None:
    old = _number(previous)
    new = _number(current)
    if old is None or new is None or old <= 0 or new <= 0:
        return None
    return (new / old - 1) * 100


def evaluate_thesis_monitoring(
    baseline: dict[str, Any] | None,
    current: dict[str, Any],
    asset_type: str,
    days_since_review: int,
) -> dict[str, Any]:
    """Compare a current snapshot with the latest baseline and classify materiality."""
    age = _number(current.get("data_age_days"))
    if age is None or age > 30 or age < 0:
        return {
            "status": "DADOS_INSUFICIENTES",
            "triggers": ["dados_desatualizados"],
            "changes": {"data_age_days": age},
        }
    if _number(current.get("price")) is None:
        return {
            "status": "DADOS_INSUFICIENTES",
            "triggers": ["preco_indisponivel"],
            "changes": {},
        }
    if baseline is None:
        return {"status": "BASELINE_CRIADO", "triggers": [], "changes": {}}

    triggers: list[str] = []
    changes: dict[str, float] = {}
    price_change = _relative_change(baseline.get("price"), current.get("price"))
    if price_change is not None:
        changes["price_pct"] = round(price_change, 2)
        if abs(price_change) >= 15:
            triggers.append("preco_desde_tese")
    daily_change = _number(current.get("daily_change_pct"))
    if daily_change is not None and abs(daily_change) >= 5:
        triggers.append("variacao_diaria")

    for key in ("p_l", "p_vp", "div_liq_patrim", "dividend_yield"):
        change = _relative_change(baseline.get(key), current.get(key))
        if change is not None:
            changes[f"{key}_pct"] = round(change, 2)
            if abs(change) >= 20:
                triggers.append(f"mudanca_{key}")
    for key in ("roe", "roic"):
        old = _number(baseline.get(key))
        new = _number(current.get(key))
        if old is not None and new is not None:
            delta = new - old
            changes[f"{key}_pp"] = round(delta, 2)
            if abs(delta) >= 3:
                triggers.append(f"mudanca_{key}")

    review_days = {
        "FII": 30, "RENDA_FIXA": 30, "ACAO": 90,
        "BDR": 90, "REIT": 90, "ETF": 180,
    }.get(str(asset_type or "").upper(), 90)
    periodic_due = days_since_review >= review_days
    if periodic_due:
        triggers.append("revisao_periodica")

    material = [trigger for trigger in triggers if trigger != "variacao_diaria"]
    if periodic_due or len(material) >= 2:
        status = "REVISAO_RECOMENDADA"
    elif triggers:
        status = "ACOMPANHAR"
    else:
        status = "SEM_MUDANCA_MATERIAL"
    return {"status": status, "triggers": triggers, "changes": changes}
