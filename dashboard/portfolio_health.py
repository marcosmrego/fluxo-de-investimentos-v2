"""Scoring explicavel da saude da carteira, sem recomendacao de investimento."""

from __future__ import annotations

import math
from collections import defaultdict


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _label(score: float) -> str:
    if score >= 80:
        return "Saudavel"
    if score >= 60:
        return "Atencao moderada"
    if score >= 40:
        return "Atencao elevada"
    return "Critica"


def compute_portfolio_health(
    positions: list[dict],
    cumulative_returns: list[float] | None = None,
    *,
    historical_data_reliable: bool = False,
) -> dict:
    """Calcula score (0-100), pilares e alertas a partir de dados serializaveis."""
    valid = [p for p in positions if float(p.get("value") or 0) > 0]
    total = sum(float(p["value"]) for p in valid)
    if total <= 0:
        return {
            "score": None,
            "classification": "Indisponivel",
            "summary": "Nao ha posicoes com valor de mercado suficiente para avaliar a carteira.",
            "pillars": [],
            "metrics": {},
            "alerts": [{"level": "critical", "text": "Complete as cotacoes das posicoes para gerar o diagnostico."}],
            "confidence": "baixa",
        }

    weights = [float(p["value"]) / total for p in valid]
    max_weight = max(weights) * 100
    effective_assets = 1 / sum(w * w for w in weights)
    diversification = _clamp(effective_assets / 10 * 100)
    concentration = _clamp(100 - max(0, max_weight - 10) * 3.5)

    sector_values: dict[str, float] = defaultdict(float)
    for p in valid:
        sector_values[p.get("sector") or "Nao classificado"] += float(p["value"])
    max_sector, max_sector_value = max(sector_values.items(), key=lambda item: item[1])
    max_sector_weight = max_sector_value / total * 100
    concentration = min(concentration, _clamp(100 - max(0, max_sector_weight - 25) * 2.5))

    coverage = sum(bool(p.get("has_quote")) for p in positions) / len(positions) * 100 if positions else 0
    registration = sum(bool(p.get("registered")) for p in positions) / len(positions) * 100 if positions else 0
    data_quality = (coverage + registration) / 2

    cumulative = [float(r) / 100 for r in (cumulative_returns or []) if r is not None]
    returns = []
    for previous, current in zip(cumulative, cumulative[1:]):
        previous_factor = 1 + previous
        if previous_factor > 0:
            returns.append((1 + current) / previous_factor - 1)
    volatility = None
    max_drawdown = None
    risk_score = 50.0
    if len(returns) >= 20:
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        volatility = math.sqrt(variance) * math.sqrt(252) * 100
        wealth = peak = 1.0
        max_drawdown = 0.0
        for value in returns:
            wealth *= 1 + value
            peak = max(peak, wealth)
            max_drawdown = min(max_drawdown, (wealth / peak - 1) * 100)
        risk_score = _clamp(100 - max(0, volatility - 8) * 2.5 - max(0, abs(max_drawdown) - 5) * 2)

    pillars = [
        {"key": "diversification", "label": "Diversificacao", "score": round(diversification)},
        {"key": "concentration", "label": "Concentracao", "score": round(concentration)},
        {"key": "risk", "label": "Risco estimado", "score": round(risk_score)},
        {"key": "data", "label": "Qualidade dos dados", "score": round(data_quality)},
    ]
    risk_weight = 0.10 if not historical_data_reliable else 0.25
    score = (
        diversification * 0.30
        + concentration * 0.35
        + risk_score * risk_weight
        + data_quality * (0.35 - risk_weight)
    )

    alerts = []
    top = valid[weights.index(max(weights))]
    if max_weight > 15:
        alerts.append({"level": "warning", "text": f"{top['ticker']} representa {max_weight:.1f}% da carteira; avalie o risco de concentracao."})
    if max_sector_weight > 30:
        alerts.append({"level": "warning", "text": f"O setor {max_sector} concentra {max_sector_weight:.1f}% do patrimonio."})
    if coverage < 100:
        alerts.append({"level": "critical", "text": f"A cobertura de cotacoes esta em {coverage:.0f}%; o score pode estar distorcido."})
    if not historical_data_reliable:
        alerts.append({"level": "info", "text": "Volatilidade e drawdown sao estimativas: o historico foi reconstruido com as posicoes atuais."})
    if not alerts:
        alerts.append({"level": "positive", "text": "Nenhum alerta relevante foi identificado pelos limites atuais."})

    rounded_score = round(score)
    weakest = sorted(pillars, key=lambda pillar: pillar["score"])[:2]
    weakest_labels = " e ".join(pillar["label"].lower() for pillar in weakest)
    return {
        "score": rounded_score,
        "classification": _label(rounded_score),
        "summary": f"A carteira esta em {_label(rounded_score).lower()}; os pilares com mais espaco para melhora sao {weakest_labels}.",
        "pillars": pillars,
        "metrics": {
            "assets": len(valid),
            "effective_assets": round(effective_assets, 1),
            "largest_position_pct": round(max_weight, 1),
            "largest_sector": max_sector,
            "largest_sector_pct": round(max_sector_weight, 1),
            "annualized_volatility_pct": round(volatility, 1) if volatility is not None else None,
            "max_drawdown_pct": round(max_drawdown, 1) if max_drawdown is not None else None,
        },
        "alerts": alerts,
        "confidence": "alta" if historical_data_reliable and coverage == 100 else "moderada" if coverage == 100 else "baixa",
        "methodology": "Score diagnostico, nao recomendacao. Pesos: diversificacao 30%, concentracao 35%, risco 10% e dados 25% enquanto o historico nao for auditavel.",
    }
