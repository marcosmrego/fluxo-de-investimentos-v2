#!/usr/bin/env python3
"""
Modulo de Risco — Volatilidade, Beta, Correlacao e Drawdown
=============================================================
Mede dispersao de retorno, volatilidade, beta vs IBOV, correlacao
e drawdown da carteira. Gera heatmap de correlacao e grafico de
drawdown, alem de formatadores para PDF (reportlab).

Integracao: importado por relatorio_executivo.py ou usado standalone.
Autor: Hermes AI Agent
Data: 2026-07-20
"""

import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import psycopg2
from collections import defaultdict
from datetime import date, datetime

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Image, Table, TableStyle

# ═══════════════════════════════════════════════════════════════════
# Configuracoes
# ═══════════════════════════════════════════════════════════════════

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_utils import DB_CONFIG

# ── Cores do tema CLEAN (mesmo padrao do relatorio principal) ────
COR = {
    "bg": "#FAFBFC",
    "card": "#FFFFFF",
    "border": "#D0D7DE",
    "text": "#1F2328",
    "muted": "#656D76",
    "accent": "#0969DA",
    "green": "#1A7F37",
    "red": "#CF222E",
    "yellow": "#9A6700",
    "orange": "#BC4C00",
    "purple": "#8250DF",
    "white": "#FFFFFF",
}

# ── Paleta de cores para graficos ────────────────────────────────
PALETA = [
    "#0969DA", "#1A7F37", "#CF222E", "#9A6700", "#8250DF",
    "#BC4C00", "#54AEFF", "#4AC26B", "#F77882", "#D4A72C",
]

# ── Estilo matplotlib do tema CLEAN ──────────────────────────────
plt.rcParams.update({
    "figure.facecolor": COR["bg"],
    "axes.facecolor": COR["card"],
    "axes.edgecolor": COR["border"],
    "axes.labelcolor": COR["text"],
    "text.color": COR["text"],
    "xtick.color": COR["muted"],
    "ytick.color": COR["muted"],
    "grid.color": COR["border"],
    "grid.alpha": 0.4,
    "font.family": "sans-serif",
    "font.size": 9,
})

# ── Landing de correlacoes para alerta setorial ──────────────────
ALERTA_LIMITE_CORR = 0.60   # Correlacao minima para gerar alerta
ALERTA_TOP_N = 20           # Numero maximo de pares no top correlacao
MIN_PONTOS_REGRESSAO = 20   # Minimo de pontos para calcular beta


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 1: COMPUTACAO DOS DADOS                   ║
# ╚══════════════════════════════════════════════════════════════════╝

def compute_risco() -> dict:
    """
    Conecta ao banco e calcula todas as metricas de risco da carteira.

    Retorna um dicionario com os blocos:
        - volatilidade: vol por ativo (30d, 90d, anualizada)
        - volatilidade_carteira: vol ponderada anualizada
        - beta: beta vs IBOV por ativo
        - correlacao: top correlacoes entre pares de ativos
        - drawdown: drawdown maximo e atual da carteira
        - resumo: metricas consolidadas

    Returns:
        dict conforme especificacao
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ══════════════════════════════════════════════════════════════
    # Carrega cotacoes de todos os tickers + IBOV
    # ══════════════════════════════════════════════════════════════
    cur.execute("""
        SELECT ticker, data, fechamento
        FROM investimentos.cotacoes
        WHERE data >= '2026-01-01'
        ORDER BY ticker, data
    """)
    rows_cot = cur.fetchall()

    # ══════════════════════════════════════════════════════════════
    # Carrega os pesos das posicoes atuais
    # ══════════════════════════════════════════════════════════════
    cur.execute("""
        SELECT p.ticker, p.custo_total
        FROM investimentos.posicoes p
        WHERE p.quantidade_total > 0
    """)
    pos_rows = cur.fetchall()

    # ══════════════════════════════════════════════════════════════
    # Carrega setores dos ativos
    # ══════════════════════════════════════════════════════════════
    cur.execute("""
        SELECT ticker, setor, tipo
        FROM investimentos.ativos
        WHERE setor IS NOT NULL AND setor != ''
    """)
    setor_map = {}
    for row in cur.fetchall():
        setor_map[row[0]] = {"setor": row[1], "tipo": row[2]}

    # ══════════════════════════════════════════════════════════════
    # Carrega rentabilidade diaria da carteira
    # ══════════════════════════════════════════════════════════════
    cur.execute("""
        SELECT data, rentabilidade
        FROM investimentos.rentabilidade_diaria
        ORDER BY data
    """)
    rent_rows = cur.fetchall()

    conn.close()

    # ══════════════════════════════════════════════════════════════
    # Organiza cotacoes por ticker em dicionarios de arrays
    # ══════════════════════════════════════════════════════════════
    ticker_prices = defaultdict(list)
    ticker_dates = defaultdict(list)

    for ticker, dt, fechamento in rows_cot:
        ticker_prices[ticker].append(float(fechamento))
        ticker_dates[ticker].append(dt)

    # ══════════════════════════════════════════════════════════════
    # Organiza pesos das posicoes
    # ══════════════════════════════════════════════════════════════
    pesos = {}
    custo_total_carteira = sum(float(row[1]) for row in pos_rows)
    for row in pos_rows:
        ticker = row[0]
        custo = float(row[1])
        pesos[ticker] = custo / custo_total_carteira if custo_total_carteira > 0 else 0.0

    # ══════════════════════════════════════════════════════════════
    # Extrai datas unicas para alinhamento dos retornos
    # Usa IBOV como referencia para o calendario de dias uteis
    # ══════════════════════════════════════════════════════════════
    ibov_dates = ticker_dates.get("IBOV", [])
    ibov_prices = ticker_prices.get("IBOV", [])

    # ══════════════════════════════════════════════════════════════
    # Calcula retornos diarios para cada ticker e IBOV
    # ══════════════════════════════════════════════════════════════
    ticker_returns = {}  # ticker -> np.array de retornos
    ticker_return_dates = {}  # ticker -> lista de datas

    # Comeca pelo IBOV
    if len(ibov_prices) >= 2:
        ibov_returns = np.diff(ibov_prices) / ibov_prices[:-1]
        ticker_returns["IBOV"] = ibov_returns
        ticker_return_dates["IBOV"] = ibov_dates[1:]  # datas alinhadas aos retornos
    else:
        ibov_returns = np.array([])
        ticker_returns["IBOV"] = np.array([])
        ticker_return_dates["IBOV"] = []

    # Demais tickers (apenas os que estao em posicoes)
    tickers_carteira = sorted(pesos.keys())
    for ticker in tickers_carteira:
        prices = np.array(ticker_prices.get(ticker, []))
        if len(prices) >= 2:
            rets = np.diff(prices) / prices[:-1]
            ticker_returns[ticker] = rets
            ticker_return_dates[ticker] = ticker_dates.get(ticker, [])[1:]
        else:
            ticker_returns[ticker] = np.array([])
            ticker_return_dates[ticker] = []

    # ══════════════════════════════════════════════════════════════
    # 1. VOLATILIDADE POR ATIVO
    # ══════════════════════════════════════════════════════════════
    volatilidade = []
    for ticker in tickers_carteira:
        rets = ticker_returns.get(ticker, np.array([]))
        if len(rets) < 5:
            volatilidade.append({
                "ticker": ticker,
                "vol_30d": None,
                "vol_90d": None,
                "vol_anualizada": None,
            })
            continue

        # Vol 30 dias uteis (janela mais recente)
        vol_30d = float(np.std(rets[-30:])) * 100 if len(rets) >= 30 else float(np.std(rets)) * 100

        # Vol 90 dias uteis
        vol_90d = float(np.std(rets[-90:])) * 100 if len(rets) >= 90 else float(np.std(rets)) * 100

        # Vol anualizada (todos os dados disponiveis)
        vol_anualizada = float(np.std(rets)) * np.sqrt(252) * 100

        volatilidade.append({
            "ticker": ticker,
            "vol_30d": round(vol_30d, 1),
            "vol_90d": round(vol_90d, 1),
            "vol_anualizada": round(vol_anualizada, 1),
        })

    # Ordena por volatilidade anualizada decrescente
    volatilidade.sort(key=lambda x: x["vol_anualizada"] or 0, reverse=True)

    # ══════════════════════════════════════════════════════════════
    # 2. VOLATILIDADE DA CARTEIRA (ponderada pelos pesos)
    # ══════════════════════════════════════════════════════════════
    vol_carteira = 0.0
    for v in volatilidade:
        if v["vol_anualizada"] is not None:
            vol_carteira += pesos.get(v["ticker"], 0) * v["vol_anualizada"]

    volatilidade_carteira = round(vol_carteira, 1)

    # ══════════════════════════════════════════════════════════════
    # 3. BETA VS IBOV (regressao linear simples)
    # ══════════════════════════════════════════════════════════════
    ibov_rets = ticker_returns.get("IBOV", np.array([]))
    beta = []

    if len(ibov_rets) >= MIN_PONTOS_REGRESSAO:
        for ticker in tickers_carteira:
            rets = ticker_returns.get(ticker, np.array([]))
            if len(rets) < MIN_PONTOS_REGRESSAO:
                beta.append({
                    "ticker": ticker,
                    "beta": None,
                    "r2": None,
                })
                continue

            # Alinha retornos com IBOV: usa o minimo de tamanho comum
            min_len = min(len(rets), len(ibov_rets))
            x = ibov_rets[-min_len:]   # IBOV eh a variavel independente
            y = rets[-min_len:]         # Ativo eh a variavel dependente

            # Remove NaNs/infs
            mask = np.isfinite(x) & np.isfinite(y)
            x_clean = x[mask]
            y_clean = y[mask]

            if len(x_clean) < MIN_PONTOS_REGRESSAO:
                beta.append({
                    "ticker": ticker,
                    "beta": None,
                    "r2": None,
                })
                continue

            # Regressao linear: y = alpha + beta * x
            coeffs = np.polyfit(x_clean, y_clean, 1)
            beta_val = coeffs[0]

            # Coeficiente de determinacao R²
            y_pred = np.polyval(coeffs, x_clean)
            ss_res = np.sum((y_clean - y_pred) ** 2)
            ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
            r2_val = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            beta.append({
                "ticker": ticker,
                "beta": round(float(beta_val), 2),
                "r2": round(float(r2_val), 2),
            })
    else:
        # Sem dados suficientes de IBOV
        for ticker in tickers_carteira:
            beta.append({"ticker": ticker, "beta": None, "r2": None})

    # Ordena por beta decrescente
    beta.sort(key=lambda x: x["beta"] if x["beta"] is not None else -999, reverse=True)

    # ══════════════════════════════════════════════════════════════
    # 4. MATRIZ DE CORRELACAO
    # ══════════════════════════════════════════════════════════════
    # Monta matriz de retornos alinhados por data
    # Primeiro, encontra a uniao de todas as datas com retornos
    all_dates_set = set()
    for ticker in tickers_carteira:
        all_dates_set.update(ticker_return_dates.get(ticker, []))
    all_dates = sorted(all_dates_set)

    # Cria um mapa data->indice para alinhamento
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    # Monta matriz N_tickers x N_datas preenchida com NaN
    n_assets = len(tickers_carteira)
    n_dates = len(all_dates)
    returns_matrix = np.full((n_assets, n_dates), np.nan)

    for i, ticker in enumerate(tickers_carteira):
        dates = ticker_return_dates.get(ticker, [])
        rets = ticker_returns.get(ticker, np.array([]))
        for j, d in enumerate(dates):
            if d in date_to_idx:
                idx = date_to_idx[d]
                returns_matrix[i, idx] = rets[j]

    # Remove colunas (datas) onde todos sao NaN
    valid_cols = ~np.all(np.isnan(returns_matrix), axis=0)
    returns_matrix = returns_matrix[:, valid_cols]

    # Remove colunas com menos de 50% dos ativos presentes
    min_present = max(3, int(n_assets * 0.5))
    valid_cols = np.sum(~np.isnan(returns_matrix), axis=0) >= min_present
    returns_matrix = returns_matrix[:, valid_cols]

    # Remove ativos que tem menos de 20 dias validos
    valid_rows = np.sum(~np.isnan(returns_matrix), axis=1) >= MIN_PONTOS_REGRESSAO
    valid_tickers = [t for i, t in enumerate(tickers_carteira) if valid_rows[i]]
    returns_matrix = returns_matrix[valid_rows, :]

    # Calcula matriz de correlacao
    correlacao = []
    if returns_matrix.shape[0] >= 2:
        corr_matrix = np.corrcoef(returns_matrix)
        # Substitui NaN por 0 na diagonal (auto-correlacao de series constantes)
        corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

        n_valid = corr_matrix.shape[0]
        # Extrai pares unicos (triangulo superior, excluindo diagonal)
        pares = []
        for i in range(n_valid):
            for j in range(i + 1, n_valid):
                corr_val = float(corr_matrix[i, j])
                pares.append({
                    "ticker1": valid_tickers[i],
                    "ticker2": valid_tickers[j],
                    "corr": round(corr_val, 4),
                })

        # Filtra por correlacao > ALERTA_LIMITE_CORR e ordena decrescente
        pares_filtrados = [p for p in pares if abs(p["corr"]) > ALERTA_LIMITE_CORR]
        pares_filtrados.sort(key=lambda x: -abs(x["corr"]))

        # Top N pares
        top_pares = pares_filtrados[:ALERTA_TOP_N]

        # Adiciona alerta setorial
        for p in top_pares:
            t1 = p["ticker1"]
            t2 = p["ticker2"]
            setor1 = setor_map.get(t1, {}).get("setor", "")
            setor2 = setor_map.get(t2, {}).get("setor", "")
            tipo1 = setor_map.get(t1, {}).get("tipo", "")
            tipo2 = setor_map.get(t2, {}).get("tipo", "")

            if setor1 and setor2 and setor1 == setor2:
                alerta = "setorial"
            elif tipo1 == tipo2 and tipo1 in ("FII",):
                # Ambos FII do mesmo segmento (ex: Papel/CRI)
                if setor1 and setor2:
                    alerta = "segmento"
                else:
                    alerta = "mesmo_tipo"
            elif tipo1 == tipo2 and tipo1 in ("ACAO",):
                alerta = "setorial"
            else:
                alerta = "diversificado"

            p["alerta"] = alerta
            p["par"] = f"{t1} x {t2}"

        correlacao = top_pares
    else:
        # Sem dados suficientes para correlacao
        correlacao = []

    # ══════════════════════════════════════════════════════════════
    # 5. DRAWDOWN DA CARTEIRA
    # ══════════════════════════════════════════════════════════════
    drawdown = _compute_drawdown(rent_rows)

    # ══════════════════════════════════════════════════════════════
    # 6. RESUMO CONSOLIDADO
    # ══════════════════════════════════════════════════════════════

    # Volatilidade anualizada media (das vols calculadas)
    vols_validas = [v["vol_anualizada"] for v in volatilidade if v["vol_anualizada"] is not None]
    vol_media = round(np.mean(vols_validas), 1) if vols_validas else 0.0

    # Beta medio
    betas_validos = [b["beta"] for b in beta if b["beta"] is not None]
    beta_medio = round(np.mean(betas_validos), 2) if betas_validos else 0.0

    # Correlacao media
    corrs = [c["corr"] for c in correlacao]
    corr_media = round(np.mean(corrs), 2) if corrs else 0.0

    # Maior correlacao
    if correlacao:
        maior = correlacao[0]
        maior_corr = (maior["ticker1"], maior["ticker2"], maior["corr"])
    else:
        maior_corr = ("", "", 0.0)

    # Concentracao setorial: setores com correlacao > 0.70
    concentracao = _compute_concentracao_setorial(correlacao, setor_map, pesos)

    resumo = {
        "vol_anualizada": round(vol_media, 1),
        "beta_medio": beta_medio,
        "corr_media": corr_media,
        "maior_corr": maior_corr,
        "concentracao_setorial": concentracao,
        "drawdown_max": drawdown["maximo"],
    }

    return {
        "volatilidade": volatilidade,
        "volatilidade_carteira": volatilidade_carteira,
        "beta": beta,
        "correlacao": correlacao,
        "drawdown": drawdown,
        "resumo": resumo,
    }


def _compute_drawdown(rent_rows: list) -> dict:
    """
    Calcula drawdown a partir da serie de rentabilidade diaria.

    A rentabilidade esta em percentual (ex: -1.3092 significa -1.3092%).
    Converte para decimal antes de calcular o acumulado.

    Args:
        rent_rows: lista de tuplas (data, rentabilidade)

    Returns:
        dict com maximo, data_inicio, data_fundo, duracao_dias, drawdown_atual
    """
    if not rent_rows:
        return {
            "maximo": 0.0,
            "data_inicio": "",
            "data_fundo": "",
            "duracao_dias": 0,
            "drawdown_atual": 0.0,
        }

    datas = [row[0] for row in rent_rows]
    retornos_pct = [float(row[1]) for row in rent_rows]

    # Converte percentual para decimal: -1.3092% -> -0.013092
    retornos = [r / 100.0 for r in retornos_pct]

    # Calcula valor acumulado: cumprod(1 + retorno)
    acumulado = np.cumprod(1.0 + np.array(retornos))

    # Peak: maximo acumulado ate o momento (rolling maximum)
    peak = np.maximum.accumulate(acumulado)

    # Drawdown: (acumulado / peak) - 1, em percentual
    dd_series = (acumulado / peak - 1.0) * 100.0

    # Drawdown maximo
    idx_min = np.argmin(dd_series)  # indice do maior drawdown (mais negativo)
    dd_max = float(dd_series[idx_min])

    # Encontra data do fundo
    data_fundo = datas[idx_min]

    # Encontra data de inicio (quando o peak foi atingido antes do fundo)
    peak_val = peak[idx_min]
    data_inicio = ""
    for i in range(idx_min, -1, -1):
        if acumulado[i] >= peak_val * 0.9999:  # Tolerancia para arredondamento
            data_inicio = datas[i]
            break

    # Duracao em dias corridos
    duracao_dias = 0
    if data_inicio and data_fundo:
        if isinstance(data_inicio, date) and isinstance(data_fundo, date):
            duracao_dias = (data_fundo - data_inicio).days
        elif isinstance(data_inicio, str):
            d1 = datetime.strptime(data_inicio, "%Y-%m-%d").date()
            d2 = datetime.strptime(str(data_fundo), "%Y-%m-%d").date()
            duracao_dias = (d2 - d1).days

    # Drawdown atual: desde o ultimo pico
    dd_atual = float(dd_series[-1])

    # Formata datas como string
    fmt_data = lambda d: d.strftime("%Y-%m-%d") if hasattr(d, 'strftime') else str(d)

    return {
        "maximo": round(dd_max, 2),
        "data_inicio": fmt_data(data_inicio) if data_inicio else "",
        "data_fundo": fmt_data(data_fundo),
        "duracao_dias": duracao_dias,
        "drawdown_atual": round(dd_atual, 2),
    }


def _compute_concentracao_setorial(
    correlacao: list,
    setor_map: dict,
    pesos: dict,
) -> str:
    """
    Analisa concentracao setorial com base nas correlacoes altas (> 0.70).

    Args:
        correlacao: lista de pares com correlacao
        setor_map: mapa ticker -> {setor, tipo}
        pesos: mapa ticker -> peso na carteira

    Returns:
        str descritiva da concentracao encontrada
    """
    # Agrupa pares com corr > 0.70 por setor
    setor_high_corr = defaultdict(set)  # setor -> set de tickers envolvidos

    for c in correlacao:
        if c["corr"] > 0.70:
            for tk in [c["ticker1"], c["ticker2"]]:
                setor_info = setor_map.get(tk, {})
                setor = setor_info.get("setor", "")
                if setor:
                    setor_high_corr[setor].add(tk)

    if not setor_high_corr:
        return "Nenhuma concentracao setorial critica detectada (corr > 0.70)."

    # Encontra o setor mais concentrado
    partes = []
    for setor, tickers in sorted(setor_high_corr.items(),
                                 key=lambda x: -len(x[1])):
        peso_total = sum(pesos.get(tk, 0) for tk in tickers) * 100
        ticker_list = ", ".join(sorted(tickers))
        partes.append(f"{setor}: {peso_total:.1f}% dos ativos com correlacao > 0.70")

    return "; ".join(partes[:3])  # Top 3 setores


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 2: GERACAO DE GRAFICOS                    ║
# ╚══════════════════════════════════════════════════════════════════╝

def _salvar_figura(fig, path: str) -> str:
    """
    Helper: salva a figura matplotlib em PNG e fecha.

    Args:
        fig: objeto Figure do matplotlib
        path: caminho completo do arquivo PNG

    Returns:
        str: caminho do arquivo salvo
    """
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight',
                facecolor=COR["bg"], edgecolor='none')
    plt.close(fig)
    return path


def grafico_heatmap_correlacao(correlacao_data: list, path: str) -> str:
    """
    Gera heatmap NxN da matriz de correlacao entre os ativos.

    Args:
        correlacao_data: saida de compute_risco()['correlacao']
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    if not correlacao_data:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, "Dados insuficientes para matriz de correlacao",
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color=COR["muted"])
        ax.set_title("Matriz de Correlacao entre Ativos",
                     color=COR["text"], fontsize=13, pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    # Extrai tickers unicos e monta matriz NxN
    tickers_set = set()
    for c in correlacao_data:
        tickers_set.add(c["ticker1"])
        tickers_set.add(c["ticker2"])
    tickers = sorted(tickers_set)

    n = len(tickers)
    if n < 2:
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.text(0.5, 0.5, f"Apenas {n} ativo(s) — correlacao requer 2+",
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color=COR["muted"])
        ax.set_title("Matriz de Correlacao entre Ativos",
                     color=COR["text"], fontsize=13, pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    # Monta matriz a partir dos pares de correlacao
    corr_map = {}
    for c in correlacao_data:
        corr_map[(c["ticker1"], c["ticker2"])] = c["corr"]
        corr_map[(c["ticker2"], c["ticker1"])] = c["corr"]

    corr_mat = np.zeros((n, n))
    for i, t1 in enumerate(tickers):
        for j, t2 in enumerate(tickers):
            if i == j:
                corr_mat[i, j] = 1.0
            else:
                corr_mat[i, j] = corr_map.get((t1, t2), 0.0)

    # Limita a max 15 ativos para legibilidade
    if n > 15:
        # Ordena por soma absoluta de correlacoes (mais "conectados" primeiro)
        soma_corr = np.sum(np.abs(corr_mat), axis=1)
        idx_top = np.argsort(soma_corr)[-15:][::-1]
        tickers = [tickers[i] for i in idx_top]
        corr_mat = corr_mat[np.ix_(idx_top, idx_top)]
        n = 15

    # Cria o heatmap
    fig, ax = plt.subplots(figsize=(max(8, n * 0.6), max(6, n * 0.55)))

    # Colormap: vermelho (corr positiva) -> branco (0) -> azul (corr negativa)
    cmap = plt.cm.RdYlBu_r  # Red-Yellow-Blue reversed: +1=red, 0=yellow, -1=blue
    im = ax.imshow(corr_mat, cmap=cmap, vmin=-1, vmax=1, aspect='auto')

    # Labels nos eixos
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(tickers, rotation=45, ha='right', fontsize=7,
                       fontfamily='monospace')
    ax.set_yticklabels(tickers, fontsize=7, fontfamily='monospace')

    # Anota os valores nas celulas
    for i in range(n):
        for j in range(n):
            val = corr_mat[i, j]
            cor_fg = 'white' if abs(val) > 0.55 else COR["text"]
            ax.text(j, i, f"{val:.2f}", ha='center', va='center',
                    fontsize=6.5, color=cor_fg, fontweight='bold')

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Correlacao", color=COR["muted"], fontsize=8)
    cbar.ax.tick_params(colors=COR["muted"], labelsize=7)

    ax.set_title("Matriz de Correlacao entre Ativos",
                 color=COR["text"], fontsize=13, pad=12, fontweight='bold')

    return _salvar_figura(fig, path)


def grafico_drawdown(drawdown_data: dict, path: str) -> str:
    """
    Gera grafico de linha/area mostrando o drawdown ao longo do tempo.

    Args:
        drawdown_data: dict com maximo, data_inicio, data_fundo, duracao_dias, etc.
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    # Carrega rentabilidade diaria novamente para plotar a serie de drawdown
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT data, rentabilidade
        FROM investimentos.rentabilidade_diaria
        ORDER BY data
    """)
    rent_rows = cur.fetchall()
    conn.close()

    if not rent_rows:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, "Sem dados de rentabilidade",
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, color=COR["muted"])
        ax.set_title("Drawdown da Carteira",
                     color=COR["text"], fontsize=13, pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    datas = [row[0] for row in rent_rows]
    retornos_pct = [float(row[1]) for row in rent_rows]
    retornos = [r / 100.0 for r in retornos_pct]

    # Calcula serie de drawdown
    acumulado = np.cumprod(1.0 + np.array(retornos))
    peak = np.maximum.accumulate(acumulado)
    dd_series = (acumulado / peak - 1.0) * 100.0

    fig, ax = plt.subplots(figsize=(10, 4.5))

    # Preenche area de drawdown
    ax.fill_between(range(len(dd_series)), dd_series, 0,
                    color=COR["red"], alpha=0.25, label="Drawdown")
    ax.plot(range(len(dd_series)), dd_series,
            color=COR["red"], linewidth=1.2, alpha=0.9)

    # Linha zero
    ax.axhline(y=0, color=COR["border"], linewidth=0.8, linestyle='-')

    # Destacar drawdown maximo com anotacao
    idx_min = np.argmin(dd_series)
    dd_max_val = float(dd_series[idx_min])

    if dd_max_val < -0.5:  # So anota se drawdown for significativo
        ax.annotate(
            f"Drawdown Max: {dd_max_val:.2f}%\n"
            f"{drawdown_data.get('data_fundo', '')}",
            xy=(idx_min, dd_max_val),
            xytext=(idx_min + len(dd_series) * 0.15, dd_max_val - 2),
            arrowprops=dict(
                arrowstyle='->',
                color=COR["red"],
                lw=1.2,
                connectionstyle='arc3,rad=0.2',
            ),
            fontsize=8,
            color=COR["red"],
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', facecolor=COR["card"],
                      edgecolor=COR["red"], alpha=0.9),
        )

    # Eixo X com datas
    step = max(1, len(datas) // 10)
    tick_positions = list(range(0, len(datas), step))
    tick_labels = []
    for i in tick_positions:
        d = datas[i]
        if hasattr(d, 'strftime'):
            tick_labels.append(d.strftime("%d/%m"))
        else:
            tick_labels.append(str(d)[-5:])

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=7)

    ax.set_title("Drawdown da Carteira",
                 color=COR["text"], fontsize=13, pad=12, fontweight='bold')
    ax.set_ylabel("Drawdown (%)", fontsize=10, color=COR["muted"])
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.grid(axis='y', alpha=0.4, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(frameon=True, fontsize=8, loc='lower left')

    return _salvar_figura(fig, path)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 3: FORMATADOR PARA PDF                    ║
# ╚══════════════════════════════════════════════════════════════════╝

def risco_para_pdf(data: dict, graficos_paths: dict,
                   styles: dict = None) -> list:
    """
    Gera uma lista de flowables do ReportLab para a secao de
    Risco e Volatilidade.

    Args:
        data: dicionario retornado por compute_risco()
        graficos_paths: dict com os caminhos dos graficos:
            {
                "heatmap_corr": str,   # path do PNG do heatmap
                "drawdown": str,       # path do PNG do drawdown
            }
        styles: dicionario opcional com estilos personalizados.
                Chaves aceitas: h1, h2, body, small, muted.

    Returns:
        Lista de flowables do ReportLab
    """
    # ── Estilos padrao ────────────────────────────────────────────
    default_styles = {
        "h1": ParagraphStyle(
            "RiscoH1",
            fontSize=16,
            textColor=COR["text"],
            spaceBefore=10,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "RiscoH2",
            fontSize=12,
            textColor=COR["accent"],
            spaceBefore=8,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "RiscoBody",
            fontSize=9,
            textColor=COR["text"],
            leading=14,
            fontName="Helvetica",
        ),
        "small": ParagraphStyle(
            "RiscoSmall",
            fontSize=8,
            textColor=COR["text"],
            leading=11,
            fontName="Helvetica",
        ),
        "muted": ParagraphStyle(
            "RiscoMuted",
            fontSize=8,
            textColor=COR["muted"],
            fontName="Helvetica-Oblique",
        ),
    }

    if styles:
        default_styles.update(styles)

    S = default_styles
    story = []

    resumo = data.get("resumo", {})
    volatilidade = data.get("volatilidade", [])
    beta_list = data.get("beta", [])
    correlacao = data.get("correlacao", [])
    drawdown = data.get("drawdown", {})
    vol_carteira = data.get("volatilidade_carteira", 0.0)

    # ── Cabecalho da secao ────────────────────────────────────────
    story.append(Paragraph("Risco e Volatilidade", S["h1"]))
    story.append(Paragraph(
        "Analise de risco da carteira: volatilidade individual e consolidada, "
        "sensibilidade ao mercado (beta vs IBOV), correlacoes entre ativos e "
        "drawdown maximo historico. Estas metricas permitem avaliar a exposicao "
        "ao risco e a diversificacao do portfolio.",
        S["body"],
    ))
    story.append(Spacer(1, 4))

    # ── Card de metricas resumo ───────────────────────────────────
    story.append(Paragraph("Resumo de Risco", S["h2"]))

    resumo_lines = [
        f"<b>Volatilidade Anualizada Media:</b> {resumo.get('vol_anualizada', 0):.1f}% "
        f"(carteira: {vol_carteira:.1f}%)",
        f"<b>Beta Medio (vs IBOV):</b> {resumo.get('beta_medio', 0):.2f}",
        f"<b>Correlacao Media entre Ativos:</b> {resumo.get('corr_media', 0):.2f}",
        f"<b>Drawdown Maximo:</b> {drawdown.get('maximo', 0):.1f}% "
        f"(de {drawdown.get('data_inicio', 'N/A')} a {drawdown.get('data_fundo', 'N/A')}, "
        f"{drawdown.get('duracao_dias', 0)} dias)",
    ]

    maior_corr = resumo.get("maior_corr", ("", "", 0.0))
    if maior_corr[0]:
        resumo_lines.append(
            f"<b>Maior Correlacao:</b> {maior_corr[0]} x {maior_corr[1]} "
            f"(corr = {maior_corr[2]:.2f})"
        )

    for line in resumo_lines:
        story.append(Paragraph(line, S["body"]))
    story.append(Spacer(1, 8))

    # ── Tabela: Top 10 ativos por volatilidade ────────────────────
    if volatilidade:
        story.append(Paragraph(
            "Top 10 Ativos por Volatilidade (Mais Volateis)", S["h2"]))
        story.append(Paragraph(
            "Volatilidade anualizada = desvio padrao dos retornos diarios * sqrt(252).",
            S["muted"],
        ))
        story.append(Spacer(1, 3))

        top_vol = [v for v in volatilidade if v["vol_anualizada"] is not None][:10]

        t_header = [
            Paragraph("<b>Ticker</b>", S["small"]),
            Paragraph("<b>Vol 30d (%)</b>", S["small"]),
            Paragraph("<b>Vol 90d (%)</b>", S["small"]),
            Paragraph("<b>Vol Anual. (%)</b>", S["small"]),
        ]
        t_data = [t_header]
        for v in top_vol:
            t_data.append([
                Paragraph(f"<b>{v['ticker']}</b>", S["small"]),
                Paragraph(
                    f"{v['vol_30d']:.1f}" if v['vol_30d'] is not None else "N/A",
                    S["small"]),
                Paragraph(
                    f"{v['vol_90d']:.1f}" if v['vol_90d'] is not None else "N/A",
                    S["small"]),
                Paragraph(
                    f"{v['vol_anualizada']:.1f}" if v['vol_anualizada'] is not None else "N/A",
                    S["small"]),
            ])

        col_w = [30 * mm, 36 * mm, 36 * mm, 40 * mm]
        t = Table(t_data, colWidths=col_w, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COR["accent"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COR["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COR["border"]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [COR["white"], HexColor("#F6F8FA")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # ── Tabela: Top 10 ativos por beta ────────────────────────────
    if beta_list:
        story.append(Paragraph(
            "Top 10 Ativos por Beta (Mais Sensiveis ao IBOV)", S["h2"]))
        story.append(Paragraph(
            "Beta > 1: mais volatil que o mercado. Beta < 1: menos volatil. "
            "R² indica o quanto da variacao do ativo e explicada pelo IBOV.",
            S["muted"],
        ))
        story.append(Spacer(1, 3))

        top_beta = [b for b in beta_list if b["beta"] is not None][:10]

        t_header = [
            Paragraph("<b>Ticker</b>", S["small"]),
            Paragraph("<b>Beta</b>", S["small"]),
            Paragraph("<b>R²</b>", S["small"]),
            Paragraph("<b>Interpretacao</b>", S["small"]),
        ]
        t_data = [t_header]
        for b in top_beta:
            # Interpretacao do beta
            beta_val = b["beta"]
            if beta_val is not None:
                if beta_val > 1.5:
                    interp = "Muito agressivo"
                elif beta_val > 1.1:
                    interp = "Agressivo"
                elif beta_val > 0.8:
                    interp = "Alinhado ao mercado"
                elif beta_val > 0.3:
                    interp = "Defensivo"
                elif beta_val > -0.3:
                    interp = "Baixa correlacao"
                else:
                    interp = "Hedge / Inverso"
            else:
                interp = "N/A"

            r2_str = f"{b['r2']:.2f}" if b['r2'] is not None else "N/A"
            beta_str = f"{b['beta']:.2f}" if b['beta'] is not None else "N/A"

            t_data.append([
                Paragraph(f"<b>{b['ticker']}</b>", S["small"]),
                Paragraph(beta_str, S["small"]),
                Paragraph(r2_str, S["small"]),
                Paragraph(interp, S["small"]),
            ])

        col_w_beta = [30 * mm, 25 * mm, 25 * mm, 62 * mm]
        t = Table(t_data, colWidths=col_w_beta, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COR["accent"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), COR["white"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("ALIGN", (1, 0), (2, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (3, 0), (3, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, COR["border"]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [COR["white"], HexColor("#F6F8FA")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # ── Heatmap de correlacao ─────────────────────────────────────
    g_heatmap = graficos_paths.get("heatmap_corr", "")
    if g_heatmap and os.path.exists(g_heatmap):
        story.append(Paragraph("Matriz de Correlacao", S["h2"]))

        if correlacao:
            story.append(Paragraph(
                f"Foram identificadas <b>{len(correlacao)} correlacoes</b> "
                f"significativas (|corr| > {ALERTA_LIMITE_CORR:.2f}) entre "
                f"os ativos da carteira.",
                S["muted"],
            ))
            story.append(Spacer(1, 3))

        story.append(Image(g_heatmap, width=150 * mm, height=120 * mm))
        story.append(Spacer(1, 8))

        # Tabela de top correlacoes com alertas
        if correlacao:
            story.append(Paragraph(
                f"Top {min(10, len(correlacao))} Correlacoes com Alerta",
                S["h2"]))

            t_header = [
                Paragraph("<b>Par</b>", S["small"]),
                Paragraph("<b>Corr</b>", S["small"]),
                Paragraph("<b>Alerta</b>", S["small"]),
            ]
            t_data = [t_header]
            for c in correlacao[:10]:
                # Cor da correlacao
                corr_val = c["corr"]
                if corr_val > 0.70:
                    cor_cor = COR["red"]
                elif corr_val > 0.50:
                    cor_cor = COR["orange"]
                else:
                    cor_cor = COR["yellow"]

                t_data.append([
                    Paragraph(f"{c['par']}", S["small"]),
                    Paragraph(f"<font color='{cor_cor}'><b>{corr_val:.2f}</b></font>",
                              S["small"]),
                    Paragraph(f"{c['alerta']}", S["small"]),
                ])

            col_w_corr = [60 * mm, 28 * mm, 54 * mm]
            t = Table(t_data, colWidths=col_w_corr, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COR["accent"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), COR["white"]),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (2, 0), (2, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, COR["border"]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [COR["white"], HexColor("#F6F8FA")]),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))

    # ── Grafico de drawdown ───────────────────────────────────────
    g_dd = graficos_paths.get("drawdown", "")
    if g_dd and os.path.exists(g_dd):
        story.append(Paragraph("Drawdown da Carteira", S["h2"]))
        story.append(Image(g_dd, width=160 * mm, height=72 * mm))
        story.append(Spacer(1, 8))

    # ── Analise textual: Principais riscos identificados ──────────
    story.append(Paragraph("Principais Riscos Identificados", S["h2"]))

    riscos = _gerar_analise_riscos(data)
    for risco in riscos:
        story.append(Paragraph(f"• {risco}", S["body"]))

    story.append(Spacer(1, 6))

    return story


def _gerar_analise_riscos(data: dict) -> list:
    """
    Gera uma lista de frases descritivas dos principais riscos
    identificados a partir dos dados computados.

    Args:
        data: dicionario retornado por compute_risco()

    Returns:
        list de str: frases de analise
    """
    riscos = []
    resumo = data.get("resumo", {})
    volatilidade = data.get("volatilidade", [])
    beta_list = data.get("beta", [])
    correlacao = data.get("correlacao", [])
    drawdown = data.get("drawdown", {})

    # Risco 1: Volatilidade da carteira
    vol_cart = data.get("volatilidade_carteira", 0)
    if vol_cart > 25:
        riscos.append(
            f"A volatilidade anualizada da carteira ({vol_cart:.1f}%) e considerada "
            f"elevada. Considere aumentar a exposicao a ativos defensivos ou "
            f"reduzir a concentracao em acoes de alta volatilidade."
        )
    elif vol_cart > 15:
        riscos.append(
            f"A volatilidade anualizada da carteira ({vol_cart:.1f}%) esta em "
            f"nivel moderado, tipico de carteiras com exposicao a acoes."
        )
    else:
        riscos.append(
            f"A volatilidade anualizada da carteira ({vol_cart:.1f}%) e baixa, "
            f"indicando bom controle de risco, provavelmente devido ao peso de "
            f"FIIs e ativos de renda na carteira."
        )

    # Risco 2: Beta vs IBOV
    beta_medio = resumo.get("beta_medio", 0)
    if beta_medio > 1.2:
        riscos.append(
            f"O beta medio da carteira ({beta_medio:.2f}) indica sensibilidade "
            f"acima do mercado. Em cenarios de queda do IBOV, a carteira tende "
            f"a cair proporcionalmente mais."
        )
    elif beta_medio > 0.5:
        riscos.append(
            f"O beta medio ({beta_medio:.2f}) mostra sensibilidade moderada ao "
            f"IBOV, com boa diversificacao entre ativos ciclicos e defensivos."
        )
    else:
        riscos.append(
            f"O beta medio baixo ({beta_medio:.2f}) indica que a carteira e "
            f"pouco correlacionada com o IBOV, o que pode ser uma protecao "
            f"em mercados de baixa, mas tambem limita ganhos em altas."
        )

    # Risco 3: Concentracao setorial (correlacao > 0.70)
    concentracao = resumo.get("concentracao_setorial", "")
    if concentracao and "Nenhuma" not in concentracao:
        riscos.append(
            f"Concentracao setorial detectada: {concentracao}. Ativos do mesmo "
            f"setor tendem a se mover juntos, reduzindo o beneficio da "
            f"diversificacao em cenarios adversos ao setor."
        )

    # Risco 4: Correlacoes altas
    altas_corr = [c for c in correlacao if c["corr"] > 0.80]
    if len(altas_corr) >= 3:
        nomes = ", ".join(c["par"] for c in altas_corr[:3])
        riscos.append(
            f"Ha {len(altas_corr)} pares de ativos com correlacao superior a 0.80 "
            f"({nomes}...). Alta correlacao reduz a diversificacao efetiva "
            f"da carteira."
        )

    # Risco 5: Drawdown
    dd_max = drawdown.get("maximo", 0)
    if dd_max < -10:
        riscos.append(
            f"O drawdown maximo de {dd_max:.1f}% (em {drawdown.get('data_fundo', 'N/A')}) "
            f"e significativo e durou {drawdown.get('duracao_dias', 0)} dias. "
            f"Este nivel de perda maxima requer alta tolerancia a risco do investidor."
        )
    elif dd_max < -5:
        riscos.append(
            f"O drawdown maximo de {dd_max:.1f}% e moderado, com duracao de "
            f"{drawdown.get('duracao_dias', 0)} dias. A carteira mostra resiliencia "
            f"razoavel em periodos de estresse."
        )
    else:
        riscos.append(
            f"O drawdown maximo de {dd_max:.1f}% e baixo, indicando boa gestao "
            f"de risco e capacidade de recuperacao da carteira."
        )

    # Risco 6: Ativo mais volatil
    if volatilidade:
        mais_vol = volatilidade[0]
        riscos.append(
            f"O ativo mais volatil e {mais_vol['ticker']} com volatilidade "
            f"anualizada de {mais_vol['vol_anualizada']:.1f}%. "
            f"Monitore a exposicao a este ativo em periodos de alta incerteza."
        )

    return riscos


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    BLOCO DE TESTE / STANDALONE                  ║
# ╚══════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    """
    Executa o modulo de forma autonoma:
    1. Computa metricas de risco
    2. Gera graficos em arquivos temporarios
    3. Exibe resumo no terminal
    4. Testa formatador PDF
    """
    import tempfile

    print("=" * 60)
    print("  MODULO DE RISCO — Teste Standalone")
    print("=" * 60)

    # ── Passo 1: Computar metricas de risco ───────────────────────
    print("\n[1/3] Computando metricas de risco...")
    data = compute_risco()

    # Exibe resumo
    resumo = data["resumo"]
    print(f"\n  Resumo de Risco:")
    print(f"    Volatilidade Anualizada Media: {resumo['vol_anualizada']:.1f}%")
    print(f"    Volatilidade Carteira:         {data['volatilidade_carteira']:.1f}%")
    print(f"    Beta Medio (vs IBOV):          {resumo['beta_medio']:.2f}")
    print(f"    Correlacao Media:              {resumo['corr_media']:.2f}")
    print(f"    Maior Correlacao:              {resumo['maior_corr']}")
    print(f"    Drawdown Maximo:               {resumo['drawdown_max']:.1f}%")
    print(f"    Concentracao Setorial:         {resumo['concentracao_setorial'][:100]}...")

    # Exibe top 5 volatilidade
    print(f"\n  Top 5 Volatilidade:")
    for v in data["volatilidade"][:5]:
        print(f"    {v['ticker']:8s}  vol_30d={v['vol_30d']:>6.1f}%  "
              f"vol_90d={v['vol_90d']:>6.1f}%  vol_anual={v['vol_anualizada']:>6.1f}%")

    # Exibe top 5 beta
    print(f"\n  Top 5 Beta (vs IBOV):")
    for b in data["beta"][:5]:
        b_str = f"{b['beta']:.2f}" if b['beta'] is not None else "N/A"
        r2_str = f"{b['r2']:.2f}" if b['r2'] is not None else "N/A"
        print(f"    {b['ticker']:8s}  beta={b_str:>6s}  r2={r2_str:>6s}")

    # Exibe top 10 correlacoes
    print(f"\n  Top 10 Correlacoes:")
    for c in data["correlacao"][:10]:
        print(f"    {c['par']:20s}  corr={c['corr']:.2f}  alerta={c['alerta']}")

    # Exibe drawdown
    dd = data["drawdown"]
    print(f"\n  Drawdown:")
    print(f"    Maximo:      {dd['maximo']:.2f}%")
    print(f"    Data Inicio: {dd['data_inicio']}")
    print(f"    Data Fundo:  {dd['data_fundo']}")
    print(f"    Duracao:     {dd['duracao_dias']} dias")
    print(f"    Atual:       {dd['drawdown_atual']:.2f}%")

    # ── Passo 2: Gerar graficos ───────────────────────────────────
    print("\n[2/3] Gerando graficos...")
    tmp = tempfile.mkdtemp(prefix="risco_")

    g_heatmap = grafico_heatmap_correlacao(
        data["correlacao"],
        os.path.join(tmp, "heatmap_correlacao.png"),
    )
    print(f"  Heatmap Correlacao → {g_heatmap}")

    g_dd = grafico_drawdown(
        data["drawdown"],
        os.path.join(tmp, "drawdown.png"),
    )
    print(f"  Drawdown           → {g_dd}")

    # ── Passo 3: Testar PDF flowables ─────────────────────────────
    print("\n[3/3] Testando formatador PDF...")
    graficos_paths = {
        "heatmap_corr": g_heatmap,
        "drawdown": g_dd,
    }
    story = risco_para_pdf(data, graficos_paths)
    print(f"  Flowables gerados: {len(story)} elementos")
    print(f"  Tipos: {', '.join(type(f).__name__ for f in story[:8])}...")

    print("\n" + "=" * 60)
    print("  TESTE CONCLUIDO COM SUCESSO")
    print(f"  Graficos em: {tmp}")
    print("=" * 60)