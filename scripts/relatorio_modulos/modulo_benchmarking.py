#!/usr/bin/env python3
"""
Modulo Benchmarking — Carteira vs CDI, Ibovespa e IFIX
=========================================================
Compara a rentabilidade real da carteira (TWR — Time-Weighted Return)
contra os principais indices do mercado brasileiro:

  - CDI:       serie sintetica (~14.15% a.a., 252 dias uteis)
  - IBOV:      Ibovespa (fechamento da tabela cotacoes)
  - IFIX:      IFIX.SA (apenas 1 registro; usa-se flat com aviso de limitacao)

Exporta:
  - compute_benchmarking()          -> dict com serie base 100 + metricas
  - grafico_benchmarking(serie, path) -> str (caminho do PNG gerado)
  - benchmarking_para_pdf(data, grafico_path) -> list (flowables ReportLab)

Integracao: importado por relatorio_executivo.py ou usado standalone.
Autor: Hermes AI Agent
Data: 2026-07-20
"""

import os
import sys
import math
from collections import OrderedDict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import psycopg2

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, Spacer, Image, Table, TableStyle, PageBreak
)

# ═══════════════════════════════════════════════════════════════════
# Constantes & configuracao
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

# ── Parametros do CDI sintetico ──────────────────────────────────
CDI_ANUAL = 0.1415       # 14.15% a.a.
DIAS_UTEIS_ANO = 252     # convencao de mercado
CDI_DIARIO = (1 + CDI_ANUAL) ** (1.0 / DIAS_UTEIS_ANO) - 1
# CDI_DIARIO ≈ 0.000524 → ~0.0524% ao dia

# Cores das series no grafico
COR_SERIES = {
    "carteira": COR["accent"],   # azul
    "cdi":      COR["green"],    # verde
    "ibov":     COR["purple"],   # roxo
    "ifix":     COR["orange"],   # laranja
}


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 1: COMPUTACAO DOS DADOS                   ║
# ╚══════════════════════════════════════════════════════════════════╝

def compute_benchmarking() -> dict:
    """
    Conecta ao banco e calcula TWR da carteira vs CDI, IBOV e IFIX.

    Retorna um dicionario com duas chaves:

        serie_twr: lista de dicts com datas e valores base 100
        resumo:     dict com metricas consolidadas (YTD, 30d, alfa, sharpe, etc.)

    Returns:
        dict {
            "serie_twr": [
                {"data": "2026-01-20", "carteira": 100.0, "cdi": 100.0,
                 "ibov": 100.0, "ifix": 100.0},
                ...
            ],
            "resumo": {
                "carteira_ytd": -0.65,
                "cdi_ytd": 2.05,
                "ibov_ytd": -1.20,
                "ifix_ytd": 0.0,
                "carteira_30d": 1.23,
                "cdi_30d": 0.58,
                "ibov_30d": -0.45,
                "alfa_vs_cdi": -2.70,
                "alfa_vs_ibov": 0.55,
                "volatilidade_carteira": 12.5,
                "sharpe": -0.22,
                "aviso_ifix": True,  # True se IFIX tem dados insuficientes
            },
        }
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ── 1. Busca rentabilidade diaria da carteira ─────────────────
    cur.execute("""
        SELECT data, rentabilidade
        FROM investimentos.rentabilidade_diaria
        ORDER BY data
    """)
    rows_carteira = cur.fetchall()
    # Converte para dicionario: data -> rentabilidade (em %)
    carteira_map = {}
    for dt, rent in rows_carteira:
        carteira_map[dt] = float(rent)

    # ── 2. Busca cotacoes do IBOV ─────────────────────────────────
    cur.execute("""
        SELECT data, fechamento
        FROM investimentos.cotacoes
        WHERE ticker = 'IBOV'
        ORDER BY data
    """)
    rows_ibov = cur.fetchall()
    ibov_map = {}
    for dt, fech in rows_ibov:
        ibov_map[dt] = float(fech)

    # ── 3. Busca cotacoes do IFIX (se houver) ─────────────────────
    cur.execute("""
        SELECT data, fechamento
        FROM investimentos.cotacoes
        WHERE ticker = 'IFIX'
        ORDER BY data
    """)
    rows_ifix = cur.fetchall()
    ifix_map = {}
    for dt, fech in rows_ifix:
        ifix_map[dt] = float(fech)

    conn.close()

    # ── 4. Constroi linha do tempo unificada ──────────────────────
    # Todas as series comecam da primeira data da carteira
    datas_carteira = sorted(carteira_map.keys())
    if not datas_carteira:
        return {
            "serie_twr": [],
            "resumo": {
                "carteira_ytd": 0.0, "cdi_ytd": 0.0, "ibov_ytd": 0.0,
                "ifix_ytd": 0.0, "carteira_30d": 0.0, "cdi_30d": 0.0,
                "ibov_30d": 0.0, "alfa_vs_cdi": 0.0, "alfa_vs_ibov": 0.0,
                "volatilidade_carteira": 0.0, "sharpe": 0.0,
                "aviso_ifix": True, "sem_dados": True,
            },
        }

    data_inicio = datas_carteira[0]

    # ── 5. Constroi serie TWR base 100 ────────────────────────────
    # IMPORTANTE: rentabilidade_diaria.rentabilidade e o retorno
    # CUMULATIVO (YTD) em percentual, nao o retorno diario.
    # Ex: rent=-1.3092 significa que a carteira esta -1.3092% desde o inicio.
    #
    # Para construir TWR base 100, convertemos o retorno cumulativo
    # para fator de crescimento e normalizamos.
    #
    # TWR_i = 100 * (1 + CR_i/100) / (1 + CR_1/100)
    # onde CR_i = rentabilidade cumulativa no dia i (em %)
    #
    # Para volatilidade/sharpe, derivamos os retornos diarios:
    #   daily_i = (1 + CR_i/100) / (1 + CR_{i-1}/100) - 1

    serie_twr = []
    retornos_diarios_carteira = []

    # Fator de normalizacao: primeiro valor da carteira = 100
    cr_primeiro = carteira_map.get(data_inicio, 0.0)
    fator_norm = 1.0 + cr_primeiro / 100.0  # growth factor do primeiro dia

    # Acumuladores
    acum_cdi = 1.0       # fator de crescimento CDI
    acum_ibov = 1.0      # fator de crescimento IBOV
    acum_ifix = 1.0      # fator de crescimento IFIX

    # Para IBOV: tracking do fechamento anterior
    ibov_anterior = ibov_map.get(data_inicio)

    # IFIX: verifica se ha dados suficientes
    ifix_suficiente = len(ifix_map) >= 5
    ifix_anterior = ifix_map.get(data_inicio) if ifix_suficiente else None

    # Guarda fator de crescimento anterior da carteira para retorno diario
    cr_anterior = None

    for i, dt in enumerate(datas_carteira):
        # --- Carteira (TWR a partir do retorno cumulativo) ---
        cr_pct = carteira_map.get(dt, 0.0)  # retorno cumulativo em %
        growth = 1.0 + cr_pct / 100.0       # fator de crescimento

        # Base 100 normalizada
        if fator_norm != 0:
            twr_val = 100.0 * growth / fator_norm
        else:
            twr_val = 100.0

        # Retorno diario (para volatilidade e sharpe)
        if cr_anterior is not None:
            daily_ret = (growth / cr_anterior) - 1.0
            retornos_diarios_carteira.append(daily_ret)
        else:
            # Primeiro dia: retorno diario = retorno cumulativo
            retornos_diarios_carteira.append(cr_pct / 100.0)

        cr_anterior = growth  # atualiza para o proximo dia

        # --- CDI (sintetico) ---
        if i == 0:
            acum_cdi = 1.0
        else:
            acum_cdi *= (1.0 + CDI_DIARIO)
        cdi_val = 100.0 * acum_cdi

        # --- IBOV ---
        fech_hoje = ibov_map.get(dt)
        if i == 0:
            acum_ibov = 1.0
            ibov_anterior = fech_hoje
        else:
            if ibov_anterior and fech_hoje and ibov_anterior > 0:
                ret_ibov = (fech_hoje / ibov_anterior) - 1.0
                acum_ibov *= (1.0 + ret_ibov)
            ibov_anterior = fech_hoje
        ibov_val = 100.0 * acum_ibov

        # --- IFIX ---
        fech_ifix = ifix_map.get(dt)
        if i == 0:
            acum_ifix = 1.0
            if ifix_suficiente:
                ifix_anterior = fech_ifix
        else:
            if ifix_suficiente and ifix_anterior and fech_ifix and ifix_anterior > 0:
                ret_ifix = (fech_ifix / ifix_anterior) - 1.0
                acum_ifix *= (1.0 + ret_ifix)
                ifix_anterior = fech_ifix
        ifix_val = 100.0 * acum_ifix

        serie_twr.append({
            "data": dt.strftime("%Y-%m-%d"),
            "carteira": round(twr_val, 2),
            "cdi": round(cdi_val, 2),
            "ibov": round(ibov_val, 2),
            "ifix": round(ifix_val, 2),
        })

    # ── 6. Calcula metricas resumo ────────────────────────────────

    # Rentabilidade YTD: usa o ultimo valor de retorno cumulativo
    ultimo_cr = carteira_map.get(datas_carteira[-1], 0.0)
    carteira_ytd = ultimo_cr  # ja e o retorno cumulativo final em %

    cdi_ytd = (acum_cdi - 1.0) * 100.0
    ibov_ytd = (acum_ibov - 1.0) * 100.0
    ifix_ytd = (acum_ifix - 1.0) * 100.0 if ifix_suficiente else 0.0

    # Rentabilidade 30 dias (ultimos ~22 dias uteis ≈ 1 mes)
    n_dias = len(datas_carteira)
    idx_30d = max(0, n_dias - 22)

    if n_dias > 1 and idx_30d > 0:
        cr_30d_antes = carteira_map.get(datas_carteira[idx_30d], 0.0)
        growth_final = 1.0 + ultimo_cr / 100.0
        growth_30d = 1.0 + cr_30d_antes / 100.0
        if growth_30d != 0:
            carteira_30d = (growth_final / growth_30d - 1.0) * 100.0
        else:
            carteira_30d = 0.0

        # CDI e IBOV usam a mesma janela de datas
        val_ini_cdi = serie_twr[idx_30d]["cdi"]
        val_ini_ibov = serie_twr[idx_30d]["ibov"]
        cdi_30d = (100.0 * acum_cdi / val_ini_cdi - 1.0) * 100.0
        ibov_30d = (100.0 * acum_ibov / val_ini_ibov - 1.0) * 100.0
    else:
        carteira_30d = carteira_ytd
        cdi_30d = cdi_ytd
        ibov_30d = ibov_ytd

    # Alfa vs CDI e vs IBOV (excesso de retorno)
    alfa_vs_cdi = carteira_ytd - cdi_ytd
    alfa_vs_ibov = carteira_ytd - ibov_ytd

    # Volatilidade anualizada da carteira
    volatilidade_carteira = _calc_volatilidade_anualizada(retornos_diarios_carteira)

    # Sharpe ratio: (retorno_carteira - CDI) / volatilidade
    # Usamos o excesso de retorno medio diario sobre CDI, anualizamos
    if volatilidade_carteira > 0 and len(retornos_diarios_carteira) > 1:
        excesso_medio_diario = np.mean(retornos_diarios_carteira) - CDI_DIARIO
        # Anualiza o excesso: excesso_medio_diario * 252
        retorno_excesso_anual = excesso_medio_diario * DIAS_UTEIS_ANO
        sharpe = retorno_excesso_anual / (volatilidade_carteira / 100.0)
    else:
        sharpe = 0.0

    return {
        "serie_twr": serie_twr,
        "resumo": {
            "carteira_ytd": round(carteira_ytd, 2),
            "cdi_ytd": round(cdi_ytd, 2),
            "ibov_ytd": round(ibov_ytd, 2),
            "ifix_ytd": round(ifix_ytd, 2),
            "carteira_30d": round(carteira_30d, 2),
            "cdi_30d": round(cdi_30d, 2),
            "ibov_30d": round(ibov_30d, 2),
            "alfa_vs_cdi": round(alfa_vs_cdi, 2),
            "alfa_vs_ibov": round(alfa_vs_ibov, 2),
            "volatilidade_carteira": round(volatilidade_carteira, 1),
            "sharpe": round(sharpe, 2),
            "aviso_ifix": not ifix_suficiente,  # True = dados insuficientes
        },
    }


def _calc_volatilidade_anualizada(retornos: list) -> float:
    """
    Calcula a volatilidade anualizada a partir de retornos diarios (decimais).

    Formula: desvio_padrao_diario * sqrt(252) * 100 (para percentual).

    Args:
        retornos: lista de retornos diarios como decimais (ex: 0.01 = 1%)

    Returns:
        float: volatilidade anualizada em percentual
    """
    if len(retornos) < 2:
        return 0.0

    arr = np.array(retornos, dtype=float)
    std_diario = np.std(arr, ddof=1)  # amostral
    vol_anual = std_diario * math.sqrt(DIAS_UTEIS_ANO) * 100.0
    return vol_anual


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 2: GERACAO DE GRAFICO                    ║
# ╚══════════════════════════════════════════════════════════════════╝

def grafico_benchmarking(serie_twr: list, path: str) -> str:
    """
    Gera grafico de linha comparando Carteira vs CDI vs IBOV vs IFIX,
    todos normalizados base 100.

    Args:
        serie_twr: lista de dicts retornada por compute_benchmarking()
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    if not serie_twr:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.text(0.5, 0.5, "Sem dados de rentabilidade",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=14, color=COR["muted"])
        ax.set_title("Benchmarking — Carteira vs Indices (Base 100)",
                     color=COR["text"], fontsize=14, pad=20, fontweight="bold")
        return _salvar_figura(fig, path)

    # Extrai dados
    datas = [s["data"] for s in serie_twr]
    datas_dt = [np.datetime64(d) for d in datas]

    y_carteira = [s["carteira"] for s in serie_twr]
    y_cdi = [s["cdi"] for s in serie_twr]
    y_ibov = [s["ibov"] for s in serie_twr]
    y_ifix = [s["ifix"] for s in serie_twr]

    # Verifica se IFIX eh flat (todos valores = 100)
    ifix_variou = any(abs(v - 100.0) > 0.01 for v in y_ifix)

    # ── Cria figura ───────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5.5))

    # Carteira — linha mais grossa, destaque
    ax.plot(datas_dt, y_carteira, color=COR_SERIES["carteira"],
            linewidth=2.2, label="Carteira", zorder=5)

    # CDI
    ax.plot(datas_dt, y_cdi, color=COR_SERIES["cdi"],
            linewidth=1.5, label="CDI", linestyle="--", zorder=4)

    # IBOV
    ax.plot(datas_dt, y_ibov, color=COR_SERIES["ibov"],
            linewidth=1.5, label="Ibovespa", linestyle="-.", zorder=4)

    # IFIX — so plota se tiver variacao; senao, nota de rodape
    if ifix_variou:
        ax.plot(datas_dt, y_ifix, color=COR_SERIES["ifix"],
                linewidth=1.5, label="IFIX", linestyle=":", zorder=4)

    # ── Linha base 100 ────────────────────────────────────────────
    ax.axhline(y=100.0, color=COR["muted"], linewidth=0.7,
               linestyle="-", alpha=0.5, zorder=1)

    # ── Formatacao dos eixos ──────────────────────────────────────
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b/%y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.tick_params(axis="x", rotation=0, labelsize=8)

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"{v:.0f}"))
    ax.set_ylabel("Base 100", color=COR["muted"], fontsize=9)

    ax.set_title("Benchmarking — Carteira vs Indices (Base 100)",
                 color=COR["text"], fontsize=13, pad=15, fontweight="bold")

    # Subtitle com periodo
    if len(datas) >= 2:
        ax.text(0.01, 0.97,
                f"{datas[0]} a {datas[-1]}",
                transform=ax.transAxes, fontsize=7.5, color=COR["muted"],
                va="top", ha="left")

    # ── Grid ──────────────────────────────────────────────────────
    ax.grid(True, linestyle="--", alpha=0.35, linewidth=0.5)

    # ── Legenda ───────────────────────────────────────────────────
    leg = ax.legend(
        loc="lower right",
        frameon=True,
        facecolor=COR["card"],
        edgecolor=COR["border"],
        fontsize=8.5,
        ncol=1,
    )

    # ── Nota IFIX se dados insuficientes ──────────────────────────
    if not ifix_variou:
        ax.text(0.98, 0.03,
                "IFIX: dados insuficientes (Yahoo nao retornou serie longa).\n"
                "Exibido como flat = 100.",
                transform=ax.transAxes, fontsize=7, color=COR["muted"],
                va="bottom", ha="right", style="italic",
                bbox=dict(facecolor=COR["bg"], edgecolor=COR["border"],
                          alpha=0.8, pad=4))

    return _salvar_figura(fig, path)


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
    fig.savefig(path, dpi=150, bbox_inches="tight",
                facecolor=COR["bg"], edgecolor="none")
    plt.close(fig)
    return path


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 3: FORMATADOR PARA PDF                   ║
# ╚══════════════════════════════════════════════════════════════════╝

def benchmarking_para_pdf(data: dict, grafico_path: str,
                          styles: dict = None) -> list:
    """
    Gera uma lista de flowables do ReportLab para a secao de
    Benchmarking (Carteira vs Indices).

    Args:
        data: dicionario retornado por compute_benchmarking()
        grafico_path: caminho do PNG gerado por grafico_benchmarking()
        styles: dicionario opcional com estilos personalizados.
                Chaves aceitas: h1, h2, body, small, muted.

    Returns:
        list de flowables do ReportLab (Paragraph, Spacer, Image, Table, etc.)
    """
    # ── Estilos padrao ────────────────────────────────────────────
    if styles is None:
        styles = {}

    h1 = styles.get("h1", ParagraphStyle(
        "BenchH1", fontName="Helvetica-Bold", fontSize=15,
        leading=20, textColor=HexColor(COR["text"]),
        spaceAfter=6 * mm, spaceBefore=4 * mm,
    ))
    h2 = styles.get("h2", ParagraphStyle(
        "BenchH2", fontName="Helvetica-Bold", fontSize=12,
        leading=16, textColor=HexColor(COR["text"]),
        spaceAfter=4 * mm, spaceBefore=10 * mm,
    ))
    body = styles.get("body", ParagraphStyle(
        "BenchBody", fontName="Helvetica", fontSize=9,
        leading=13, textColor=HexColor(COR["text"]),
        spaceAfter=3 * mm,
    ))
    small = styles.get("small", ParagraphStyle(
        "BenchSmall", fontName="Helvetica-Oblique", fontSize=7.5,
        leading=10, textColor=HexColor(COR["muted"]),
        spaceAfter=2 * mm,
    ))
    muted = styles.get("muted", ParagraphStyle(
        "BenchMuted", fontName="Helvetica-Oblique", fontSize=8,
        leading=11, textColor=HexColor(COR["muted"]),
        spaceAfter=3 * mm,
    ))

    resumo = data.get("resumo", {})
    flowables = []

    # ── 1. Titulo e introducao ────────────────────────────────────
    flowables.append(Paragraph("Benchmarking", h1))

    flowables.append(Paragraph(
        "O <b>Time-Weighted Return (TWR)</b> mede a rentabilidade real da "
        "carteira, eliminando o efeito de aportes e resgates. "
        "Abaixo, comparamos a performance da sua carteira contra o "
        "<b>CDI</b> (referencia de renda fixa), o <b>Ibovespa</b> "
        "(principal indice de acoes brasileiras) e o <b>IFIX</b> "
        "(indice de fundos imobiliarios), todos normalizados para base 100 "
        "no inicio do periodo.",
        body,
    ))

    # ── Aviso sobre CDI/IFIX ──────────────────────────────────────
    notas = [
        "CDI: serie sintetica calculada a 14,15% a.a. (252 dias uteis). "
        "Nao reflete a Selic-over diaria real.",
    ]
    if resumo.get("aviso_ifix", True):
        notas.append(
            "IFIX: dados insuficientes (Yahoo Finance nao retornou serie "
            "longa para IFIX.SA). Serie exibida como flat = 100."
        )

    flowables.append(Paragraph(
        "<font color='{}'>Nota: {}</font>".format(COR["muted"], " | ".join(notas)),
        small,
    ))
    flowables.append(Spacer(1, 4 * mm))

    # ── 2. Tabela de metricas ─────────────────────────────────────
    flowables.append(Paragraph("Metricas Comparativas", h2))

    tabela_metricas = _criar_tabela_metricas(resumo)
    flowables.append(tabela_metricas)
    flowables.append(Spacer(1, 6 * mm))

    # ── 3. Grafico ────────────────────────────────────────────────
    if os.path.exists(grafico_path):
        flowables.append(Paragraph("Evolucao Base 100", h2))
        img = Image(grafico_path, width=170 * mm, height=93.5 * mm)
        flowables.append(img)
        flowables.append(Spacer(1, 4 * mm))

    # ── 4. Analise textual ────────────────────────────────────────
    flowables.append(Paragraph("Analise de Performance", h2))

    alfa_cdi = resumo.get("alfa_vs_cdi", 0.0)
    alfa_ibov = resumo.get("alfa_vs_ibov", 0.0)
    sharpe = resumo.get("sharpe", 0.0)
    vol = resumo.get("volatilidade_carteira", 0.0)

    # Texto dinamico baseado nos resultados
    if alfa_cdi > 0:
        txt_cdi = (
            f"A carteira esta <b>{abs(alfa_cdi):.1f} pp acima</b> do CDI "
            f"no periodo, gerando alfa positivo."
        )
    elif alfa_cdi < 0:
        txt_cdi = (
            f"A carteira esta <b>{abs(alfa_cdi):.1f} pp abaixo</b> do CDI "
            f"no periodo, com alfa negativo."
        )
    else:
        txt_cdi = "A carteira esta empatada com o CDI no periodo."

    if alfa_ibov > 0:
        txt_ibov = (
            f"Em relacao ao Ibovespa, a carteira supera o indice em "
            f"<b>{alfa_ibov:.1f} pp</b>."
        )
    elif alfa_ibov < 0:
        txt_ibov = (
            f"Em relacao ao Ibovespa, a carteira fica "
            f"<b>{abs(alfa_ibov):.1f} pp abaixo</b> do indice."
        )
    else:
        txt_ibov = "A carteira esta alinhada com o Ibovespa no periodo."

    # Interpretacao do Sharpe
    if sharpe > 1.0:
        txt_sharpe = "excelente"
    elif sharpe > 0.5:
        txt_sharpe = "boa"
    elif sharpe > 0.0:
        txt_sharpe = "modesta"
    elif sharpe > -0.5:
        txt_sharpe = "ruim"
    else:
        txt_sharpe = "muito ruim"

    analise = (
        f"{txt_cdi} {txt_ibov}<br/><br/>"
        f"A volatilidade anualizada da carteira e de "
        f"<b>{vol:.1f}%</b>. O indice de Sharpe (excesso de retorno sobre "
        f"CDI dividido pela volatilidade) e de <b>{sharpe:.2f}</b>, "
        f"indicando uma relacao risco-retorno <b>{txt_sharpe}</b>."
    )

    flowables.append(Paragraph(analise, body))

    return flowables


def _criar_tabela_metricas(resumo: dict) -> Table:
    """
    Cria uma Table do ReportLab com as metricas comparativas:

        Indicador          | Carteira | CDI    | IBOV
        Rentabilidade YTD  | -0.65%   | 2.05%  | -1.20%
        Rentabilidade 30d  | 1.23%    | 0.58%  | -0.45%
        Volatilidade (anual)| 12.5%   | —      | —
        Alfa vs CDI        | -2.70 pp | —      | —
        Sharpe              | -0.22    | —      | —

    Args:
        resumo: dicionario de metricas retornado por compute_benchmarking()

    Returns:
        Table do ReportLab
    """
    # Define cores para valores positivos/negativos
    def _fmt_pct(val):
        """Formata percentual com cor: verde se >= 0, vermelho se < 0."""
        return val

    def _cor_pct(val):
        if val >= 0:
            return COR["green"]
        return COR["red"]

    # Extrai valores
    cart_ytd = resumo.get("carteira_ytd", 0.0)
    cdi_ytd = resumo.get("cdi_ytd", 0.0)
    ibov_ytd = resumo.get("ibov_ytd", 0.0)
    cart_30d = resumo.get("carteira_30d", 0.0)
    cdi_30d = resumo.get("cdi_30d", 0.0)
    ibov_30d = resumo.get("ibov_30d", 0.0)
    alfa_cdi = resumo.get("alfa_vs_cdi", 0.0)
    alfa_ibov = resumo.get("alfa_vs_ibov", 0.0)
    vol = resumo.get("volatilidade_carteira", 0.0)
    sharpe = resumo.get("sharpe", 0.0)

    # Helper para celula de percentual com cor
    def pct_cell(val, sig="%"):
        sinal = "+" if val > 0 else ""
        return Paragraph(
            "<font color='{}'>{}{:.2f}{}</font>".format(
                _cor_pct(val), sinal, val, sig
            ),
            ParagraphStyle("CellPct", fontName="Helvetica", fontSize=8.5,
                           leading=12, alignment=TA_CENTER),
        )

    def text_cell(txt):
        return Paragraph(
            txt,
            ParagraphStyle("CellTxt", fontName="Helvetica", fontSize=8.5,
                           leading=12, alignment=TA_CENTER),
        )

    def header_cell(txt):
        return Paragraph(
            "<b>{}</b>".format(txt),
            ParagraphStyle("CellHdr", fontName="Helvetica-Bold", fontSize=8.5,
                           leading=12, alignment=TA_CENTER,
                           textColor=HexColor(COR["accent"])),
        )

    def label_cell(txt):
        return Paragraph(
            "<b>{}</b>".format(txt),
            ParagraphStyle("CellLbl", fontName="Helvetica-Bold", fontSize=8.5,
                           leading=12, alignment=TA_LEFT),
        )

    dash = text_cell("—")

    # Monta tabela
    data = [
        [header_cell("Indicador"), header_cell("Carteira"),
         header_cell("CDI"), header_cell("Ibovespa")],
        [label_cell("Rentabilidade YTD"),
         pct_cell(cart_ytd), pct_cell(cdi_ytd), pct_cell(ibov_ytd)],
        [label_cell("Rentabilidade 30d"),
         pct_cell(cart_30d), pct_cell(cdi_30d), pct_cell(ibov_30d)],
        [label_cell("Alfa vs CDI"),
         pct_cell(alfa_cdi, " pp"), dash, dash],
        [label_cell("Alfa vs IBOV"),
         pct_cell(alfa_ibov, " pp"), dash, dash],
        [label_cell("Volatilidade (anual.)"),
         text_cell("{:.1f}%".format(vol)), dash, dash],
        [label_cell("Sharpe"),
         text_cell("{:.2f}".format(sharpe)), dash, dash],
    ]

    col_widths = [52 * mm, 35 * mm, 35 * mm, 40 * mm]

    tabela = Table(data, colWidths=col_widths, repeatRows=1)

    # Estilo da tabela
    estilo = TableStyle([
        # Fundo do cabecalho
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(COR["card"])),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, HexColor(COR["accent"])),
        # Linhas entre registros
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, HexColor(COR["border"])),
        # Alinhamento
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        # Fundo alternado nas linhas
        ("BACKGROUND", (0, 1), (-1, 1), HexColor("#F6F8FA")),
        ("BACKGROUND", (0, 3), (-1, 3), HexColor("#F6F8FA")),
        ("BACKGROUND", (0, 5), (-1, 5), HexColor("#F6F8FA")),
    ])

    tabela.setStyle(estilo)
    return tabela


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 4: EXECUCAO STANDALONE                   ║
# ╚══════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    """
    Teste standalone: executa compute_benchmarking, gera grafico e
    imprime metricas no terminal.
    """
    print("=" * 65)
    print("  Modulo Benchmarking — Carteira vs CDI / IBOV / IFIX")
    print("=" * 65)
    print()

    # Diretorio de saida para o grafico
    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "output"
    )
    os.makedirs(output_dir, exist_ok=True)

    # 1. Computa dados
    print("[1/3] Computando TWR e metricas...")
    resultado = compute_benchmarking()
    resumo = resultado["resumo"]

    if resumo.get("sem_dados"):
        print("  ! Sem dados de rentabilidade disponiveis.")
        sys.exit(0)

    print(f"  OK: {len(resultado['serie_twr'])} dias na serie.")

    # 2. Metricas
    print()
    print("[2/3] Metricas comparativas:")
    print(f"  Carteira YTD:         {resumo['carteira_ytd']:+.2f}%")
    print(f"  CDI YTD:              {resumo['cdi_ytd']:+.2f}%")
    print(f"  IBOV YTD:             {resumo['ibov_ytd']:+.2f}%")
    print(f"  IFIX YTD:             {resumo['ifix_ytd']:+.2f}%")
    print(f"  ---")
    print(f"  Alfa vs CDI:          {resumo['alfa_vs_cdi']:+.2f} pp")
    print(f"  Alfa vs IBOV:         {resumo['alfa_vs_ibov']:+.2f} pp")
    print(f"  Volatilidade (anual): {resumo['volatilidade_carteira']:.1f}%")
    print(f"  Sharpe:               {resumo['sharpe']:.2f}")

    if resumo.get("aviso_ifix"):
        print()
        print("  ! IFIX: dados insuficientes (apenas 1 registro). Serie flat = 100.")

    # 3. Grafico
    print()
    print("[3/3] Gerando grafico...")
    grafico_path = os.path.join(output_dir, "benchmarking.png")
    path = grafico_benchmarking(resultado["serie_twr"], grafico_path)
    print(f"  OK: {path}")

    print()
    print("=" * 65)
    print("  Concluido.")
    print("=" * 65)