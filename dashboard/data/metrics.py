"""Cálculos financeiros — TWR, Bazin, Graham."""

import numpy as np
import pandas as pd


def twr(valores_diarios: pd.DataFrame) -> float:
    """
    Time-Weighted Return (rentabilidade ponderada no tempo).
    valores_diarios: DataFrame com colunas 'rentabilidade' (em %).
    """
    if valores_diarios.empty or 'rentabilidade' not in valores_diarios.columns:
        return 0.0
    returns = valores_diarios['rentabilidade'].dropna() / 100
    if len(returns) == 0:
        return 0.0
    cumulative = np.prod(1 + returns) - 1
    return round(cumulative * 100, 2)


def bazin_preco_teto(dy_medio_5a: float, payout_ideal: float = 0.06) -> float:
    """
    Preço-teto Décio Bazin.
    Preço máximo = (Dividendo anual projetado) / (yield desejado)
    dy_medio_5a: dividend yield médio dos últimos 5 anos (em %)
    payout_ideal: yield desejado pelo investidor (default 6%)
    """
    if not dy_medio_5a or dy_medio_5a <= 0:
        return 0.0
    # Simplificação: usa o DY como proxy do dividendo
    return round(dy_medio_5a / payout_ideal, 2)


def graham_preco_justo(lpa: float, vpa: float) -> float:
    """
    Fórmula de Benjamin Graham: √(22.5 × LPA × VPA)
    """
    if not lpa or not vpa or lpa <= 0 or vpa <= 0:
        return 0.0
    return round(np.sqrt(22.5 * lpa * vpa), 2)


def percentual_carteira(saldo_atual, total_carteira) -> float:
    """% que um ativo representa na carteira."""
    saldo_atual = float(saldo_atual or 0)
    total_carteira = float(total_carteira or 0)
    if total_carteira <= 0:
        return 0.0
    return round((saldo_atual / total_carteira) * 100, 2)


def yield_on_cost(proventos_12m, custo_total) -> float:
    """Yield on cost: proventos 12m / custo total."""
    proventos_12m = float(proventos_12m or 0)
    custo_total = float(custo_total or 0)
    if custo_total <= 0:
        return 0.0
    return round((proventos_12m / custo_total) * 100, 2)