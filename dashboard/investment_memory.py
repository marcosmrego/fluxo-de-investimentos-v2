"""Pure domain rules for the portfolio investment-memory inventory."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
import math
from typing import Any, Iterable


class ThesisOrigin(str, Enum):
    """How much historical certainty exists for a position thesis."""

    CONTEMPORARY = "TESE_CONTEMPORANEA"
    RECONSTRUCTED_CURRENT = "TESE_ATUAL_RECONSTRUIDA"
    UNKNOWN = "ORIGEM_DESCONHECIDA"


_RISKS_BY_TYPE = {
    "ACAO": ["Deterioracao operacional", "Valuation e risco especifico do emissor"],
    "FII": ["Vacancia ou inadimplencia", "Juros e qualidade dos ativos"],
    "ETF": ["Risco de mercado do indice", "Concentracao da carteira do fundo"],
    "RENDA_FIXA": ["Credito do emissor", "Liquidez e marcacao a mercado"],
    "REIT": ["Juros", "Vacancia e cambio"],
    "BDR": ["Risco do emissor", "Cambio e liquidez local"],
}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _pt(value: float, suffix: str = "") -> str:
    return f"{value:.2f}".replace(".", ",") + suffix


def generate_fundamental_proposal(
    position: dict[str, Any], indicators: dict[str, Any] | None, *, as_of: str | None = None
) -> dict[str, Any]:
    """Generate a factual, reproducible draft from currently stored metrics."""
    ticker = _ticker(position.get("ticker"))
    asset_type = str(position.get("asset_type") or "NAO_CLASSIFICADO").upper()
    source = indicators or {}
    all_specs = {
        "p_l": ("P/L", ""),
        "p_vp": ("P/VP", ""),
        "roe": ("ROE", "%"),
        "roic": ("ROIC", "%"),
        "dividend_yield": ("DY", "%"),
        "div_liq_patrim": ("divida liquida/patrimonio", ""),
        "cres_rec_5a": ("crescimento de receita em 5 anos", "%"),
        "osc_12m": ("oscilacao em 12 meses", "%"),
    }
    applicable = {
        "ACAO": ("p_l", "p_vp", "roe", "roic", "dividend_yield", "div_liq_patrim", "cres_rec_5a"),
        "BDR": ("p_l", "p_vp", "roe", "roic", "dividend_yield", "div_liq_patrim", "cres_rec_5a"),
        "FII": ("p_vp", "dividend_yield", "osc_12m"),
    }.get(asset_type, ())
    metrics = {
        key: value for key in applicable
        if (value := _number(source.get(key))) is not None
    }
    facts = [
        f"{label} {_pt(metrics[key], suffix)}"
        for key, (label, suffix) in all_specs.items() if key in metrics
    ]
    name = str(position.get("name") or ticker).strip()
    sector = str(position.get("sector") or "setor nao classificado").strip()
    if facts:
        summary = (
            f"Proposta automatica para revisar {name} ({ticker}), exposicao a {sector}. "
            f"Dados observados: {', '.join(facts)}. "
            "Esta leitura e descritiva e precisa ser confrontada com a estrategia da carteira."
        )
    else:
        summary = (
            f"Proposta inicial para revisar {name} ({ticker}), exposicao a {sector}. "
            "Nao ha fundamentos estruturados suficientes para uma avaliacao quantitativa."
        )
    evidence_date = None
    evidence_age_days = None
    if source.get("data_coleta"):
        try:
            evidence_date = date.fromisoformat(str(source["data_coleta"])[:10])
            reference_date = date.fromisoformat(as_of) if as_of else date.today()
            evidence_age_days = (reference_date - evidence_date).days
        except ValueError:
            evidence_date = None
    if not applicable:
        gaps = [f"analise fundamental nao suportada para {asset_type}"]
        confidence = "baixa"
    else:
        gaps = [key for key in applicable if key not in metrics]
        if not indicators:
            gaps.insert(0, "fundamentos indisponiveis")
        coverage = len(metrics) / len(applicable)
        fresh = evidence_age_days is not None and 0 <= evidence_age_days <= 7
        acceptable = evidence_age_days is not None and 0 <= evidence_age_days <= 30
        confidence = (
            "alta" if coverage >= 0.7 and fresh
            else "moderada" if coverage >= 0.4 and acceptable
            else "baixa"
        )
    triggers_by_type = {
        "ACAO": ["Nova divulgacao de resultados", "Mudanca material nos indicadores usados nesta proposta"],
        "BDR": ["Nova divulgacao de resultados", "Mudanca material nos indicadores ou no cambio"],
        "FII": ["Novo relatorio gerencial", "Mudanca material em vacancia, rendimentos ou valor patrimonial"],
        "ETF": ["Mudanca no indice, estrategia ou composicao do fundo"],
        "RENDA_FIXA": ["Mudanca de credito do emissor, liquidez ou proximidade do vencimento"],
    }
    return {
        "ticker": ticker,
        "summary": summary,
        "horizon": "A definir apos revisao da estrategia pessoal",
        "risks": list(_RISKS_BY_TYPE.get(
            asset_type, ["Riscos especificos ainda precisam ser revisados"]
        )),
        "review_triggers": triggers_by_type.get(asset_type, [
            "Revisao manual dos eventos relevantes para esta classe"
        ]) + ["Alteracao relevante do peso ou papel do ativo na carteira"],
        "metrics": metrics,
        "confidence": confidence,
        "evidence_date": evidence_date.isoformat() if evidence_date else None,
        "evidence_age_days": evidence_age_days,
        "data_gaps": gaps,
        "methodology": "Proposta deterministica baseada nos dados estruturados mais recentes; nao e recomendacao.",
    }


def create_initial_thesis_draft(
    position: dict[str, Any], *, recorded_at: str | None
) -> dict[str, Any]:
    """Create an honest review draft from classification data only."""

    ticker = _ticker(position.get("ticker"))
    name = str(position.get("name") or ticker).strip()
    asset_type = str(position.get("asset_type") or "NAO_CLASSIFICADO").strip().upper()
    sector = str(position.get("sector") or "setor nao classificado").strip()
    return {
        "ticker": ticker,
        "origin": ThesisOrigin.UNKNOWN.value,
        "status": "RASCUNHO",
        "summary": (
            f"Tese inicial reconstruida para revisar o papel de {name} como "
            f"exposicao a {sector}. Nao representa a justificativa original da compra."
        ),
        "recorded_at": recorded_at,
        "decision_at": None,
        "horizon": "A definir na revisao",
        "risks": _RISKS_BY_TYPE.get(
            asset_type, ["Riscos especificos ainda precisam ser revisados"]
        ),
        "review_triggers": [
            "Revisao manual da tese",
            "Mudanca material nos fundamentos ou na funcao do ativo na carteira",
        ],
        "source_scope": "classificacao_atual_da_carteira",
    }


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of non-empty texts")
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one non-empty text")
    return cleaned


def validate_thesis_publication(
    payload: dict[str, Any], *, recorded_at: str | None = None
) -> dict[str, Any]:
    """Validate the human-reviewed content that can become an immutable version."""

    origin = payload.get("origin")
    allowed = {
        ThesisOrigin.RECONSTRUCTED_CURRENT.value,
        ThesisOrigin.CONTEMPORARY.value,
    }
    if origin not in allowed:
        raise ValueError("origin must identify a reviewed thesis")

    summary = str(payload.get("summary") or "").strip()
    if len(summary) < 20:
        raise ValueError("summary must contain at least 20 characters")
    horizon = str(payload.get("horizon") or "").strip()
    if not horizon:
        raise ValueError("horizon is required")

    result = {
        "origin": origin,
        "status": "PUBLICADA",
        "summary": summary,
        "horizon": horizon,
        "risks": _text_list(payload.get("risks"), "risks"),
        "review_triggers": _text_list(
            payload.get("review_triggers"), "review_triggers"
        ),
        "decision_at": payload.get("decision_at"),
    }
    if origin == ThesisOrigin.CONTEMPORARY.value:
        if not result["decision_at"]:
            raise ValueError("decision_at is required for contemporary thesis")
        decision = _aware_datetime(result["decision_at"], "decision_at", "thesis")
        if recorded_at:
            recorded = _aware_datetime(recorded_at, "recorded_at", "thesis")
            if abs(recorded - decision) > timedelta(hours=24):
                raise ValueError("contemporary thesis must be published within 24 hours")
    return result


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
    if thesis.get("status") != "PUBLICADA":
        return False
    risks = thesis.get("risks")
    review_triggers = thesis.get("review_triggers")
    valid_risks = isinstance(risks, list) and any(
        str(item).strip() for item in risks
    )
    valid_triggers = isinstance(review_triggers, list) and any(
        str(item).strip() for item in review_triggers
    )
    return all((
        bool(str(thesis.get("summary") or "").strip()),
        bool(str(thesis.get("horizon") or "").strip()),
        valid_risks,
        valid_triggers,
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
        recorded_at = None
        if origin != ThesisOrigin.UNKNOWN.value:
            recorded_at = _aware_datetime(
                thesis.get("recorded_at"), "recorded_at", ticker
            )
        if origin == ThesisOrigin.CONTEMPORARY.value and not thesis.get("decision_at"):
            raise ValueError(f"decision_at is required for contemporary thesis {ticker}")
        if origin == ThesisOrigin.CONTEMPORARY.value:
            decision_at = _aware_datetime(thesis["decision_at"], "decision_at", ticker)
            if recorded_at - decision_at > timedelta(hours=24):
                raise ValueError(
                    f"recorded_at must be within 24 hours after decision_at for {ticker}"
                )

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
            "thesis_status": thesis.get("status") if thesis else None,
            "risks": list(thesis.get("risks") or []) if thesis else [],
            "review_triggers": list(thesis.get("review_triggers") or []) if thesis else [],
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
