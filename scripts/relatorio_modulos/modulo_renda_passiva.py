#!/usr/bin/env python3
"""
Modulo de Renda Passiva e Proventos
====================================
Analisa o historico de proventos (dividendos/JCP/rendimentos),
calcula dividend yield on cost, projecao de renda passiva e gera
formatadores para PDF (reportlab) e Telegram.

Autor: Hermes AI Agent
Data: 2026-07-19
"""

import os
import psycopg2
from collections import defaultdict
from datetime import date, datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import mm, inch

# ---------------------------------------------------------------------------
# Configuracoes
# ---------------------------------------------------------------------------

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_utils import DB_CONFIG

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

PALETA = ["#0969DA", "#1A7F37", "#CF222E", "#9A6700", "#8250DF",
          "#BC4C00", "#54AEFF", "#4AC26B", "#F77882", "#D4A72C"]

# Configuracao global do matplotlib
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
    "font.size": 9,
})


# ---------------------------------------------------------------------------
# Funcao auxiliar: formatar reais
# ---------------------------------------------------------------------------

def _fmt_reais(valor: float) -> str:
    """Formata valor monetario: R$ 1.234,56."""
    if valor < 0:
        return f"-R$ {abs(valor):,.2f}"
    return f"R$ {valor:,.2f}"


# ---------------------------------------------------------------------------
# Funcao 1: compute_renda_passiva()
# ---------------------------------------------------------------------------

def compute_renda_passiva() -> dict:
    """
    Conecta ao banco de dados e calcula todas as metricas de renda passiva.

    Returns:
        dict com a estrutura:
        {
            "proventos_por_mes": [ {mes, total, tickers}, ... ],
            "proventos_por_ativo": [ {ticker, qtd, pm, proventos_12m,
                                      yield_on_cost, media_mensal,
                                      ultimo_provento, frequencia_meses,
                                      tipo}, ... ],
            "resumo": { total_12m, media_mensal_12m, yield_on_cost_carteira,
                        melhor_mes, melhor_mes_valor, projecao_proximo_mes,
                        tickers_com_proventos, total_registros },
        }
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Busca posicoes e ativos para cruzar com proventos
    # ------------------------------------------------------------------
    cur.execute("""
        SELECT p.ticker, p.quantidade_total, p.preco_medio, p.custo_total,
               a.tipo, a.nome
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        WHERE p.quantidade_total > 0
    """)
    posicoes = {}
    for row in cur.fetchall():
        ticker = row[0]
        posicoes[ticker] = {
            "qtd": float(row[1]),
            "pm": float(row[2]),
            "custo_total": float(row[3]),
            "tipo": row[4] or "",
            "nome": row[5] or "",
        }

    # ------------------------------------------------------------------
    # Busca todos os proventos, com join para pegar o tipo
    # ------------------------------------------------------------------
    cur.execute("""
        SELECT p.ticker, p.data_pgto, p.valor, p.tipo
        FROM investimentos.proventos p
        ORDER BY p.ticker, p.data_pgto
    """)
    proventos_raw = cur.fetchall()
    total_registros = len(proventos_raw)

    conn.close()

    # ------------------------------------------------------------------
    # Multiplica valor (per share) pela quantidade em carteira
    # ------------------------------------------------------------------
    # Agrupa proventos por mes e por ativo (valor total = valor * qtd)
    proventos_por_mes_dict = defaultdict(lambda: {"total": 0.0, "tickers": set()})
    proventos_por_ativo_dict = defaultdict(list)

    hoje = date.today()
    data_12m = hoje.replace(year=hoje.year - 1)

    for ticker, data_pgto, valor_per_share, tipo_provento in proventos_raw:
        pos = posicoes.get(ticker)
        if pos is None:
            continue  # Ativo nao esta mais na carteira

        qtd = pos["qtd"]
        valor_total = float(valor_per_share) * qtd

        mes_str = data_pgto.strftime("%Y-%m")
        proventos_por_mes_dict[mes_str]["total"] += valor_total
        proventos_por_mes_dict[mes_str]["tickers"].add(ticker)

        proventos_por_ativo_dict[ticker].append({
            "data": data_pgto,
            "valor_total": round(valor_total, 2),
            "tipo_provento": tipo_provento,
        })

    # ------------------------------------------------------------------
    # Converte proventos_por_mes para lista ordenada
    # ------------------------------------------------------------------
    proventos_por_mes = []
    for mes in sorted(proventos_por_mes_dict.keys()):
        info = proventos_por_mes_dict[mes]
        proventos_por_mes.append({
            "mes": mes,
            "total": round(info["total"], 2),
            "tickers": sorted(info["tickers"]),
        })

    # ------------------------------------------------------------------
    # Calcula metricas por ativo (12 meses, yield on cost, etc.)
    # ------------------------------------------------------------------
    proventos_por_ativo = []
    custo_total_carteira = sum(p["custo_total"] for p in posicoes.values())

    for ticker, pagamentos in sorted(proventos_por_ativo_dict.items()):
        pos = posicoes[ticker]
        qtd = pos["qtd"]
        pm = pos["pm"]
        custo = pos["custo_total"]

        # Ordena por data
        pagamentos.sort(key=lambda x: x["data"])

        # Proventos nos ultimos 12 meses
        proventos_12m = sum(
            p["valor_total"] for p in pagamentos
            if p["data"] >= data_12m
        )

        # Se o historico comecou depois de 04/2026 (carteira nova),
        # usa todo o periodo disponivel
        primeiro_pgto = pagamentos[0]["data"]
        if primeiro_pgto >= date(2026, 4, 1):
            proventos_12m = sum(p["valor_total"] for p in pagamentos)
            meses_ativos = max(1, (hoje.year - primeiro_pgto.year) * 12 + (hoje.month - primeiro_pgto.month) + 1)
            media_mensal = round(proventos_12m / meses_ativos, 2)
        else:
            # Conta quantos meses distintos nos ultimos 12 meses
            meses_12m = len(set(
                p["data"].strftime("%Y-%m") for p in pagamentos
                if p["data"] >= data_12m
            ))
            media_mensal = round(proventos_12m / max(1, meses_12m), 2)

        # Yield on cost: (proventos_12m / custo_total) * 100
        if custo > 0:
            yield_on_cost = round((proventos_12m / custo) * 100, 2)
        else:
            yield_on_cost = 0.0

        # Ultimo provento
        ultimo_provento = pagamentos[-1]["valor_total"] if pagamentos else 0.0

        # Frequencia media entre pagamentos (em meses)
        if len(pagamentos) >= 2:
            # Calcula intervalo medio entre pagamentos
            intervalos = []
            for i in range(1, len(pagamentos)):
                delta = (pagamentos[i]["data"] - pagamentos[i-1]["data"]).days
                intervalos.append(delta)
            intervalo_medio_dias = sum(intervalos) / len(intervalos)
            frequencia_meses = max(1, round(intervalo_medio_dias / 30.0))
        else:
            frequencia_meses = 1  # Assume mensal se so tem 1 pagamento

        proventos_por_ativo.append({
            "ticker": ticker,
            "qtd": qtd,
            "pm": pm,
            "custo_total": custo,
            "tipo": pos["tipo"],
            "nome": pos["nome"],
            "proventos_12m": round(proventos_12m, 2),
            "yield_on_cost": yield_on_cost,
            "media_mensal": media_mensal,
            "ultimo_provento": round(ultimo_provento, 2),
            "frequencia_meses": frequencia_meses,
        })

    # Ordena por yield on cost decrescente
    proventos_por_ativo.sort(key=lambda x: x["yield_on_cost"], reverse=True)

    # ------------------------------------------------------------------
    # Resumo
    # ------------------------------------------------------------------
    total_12m = round(sum(a["proventos_12m"] for a in proventos_por_ativo), 2)

    # Media mensal 12m
    # Conta meses distintos nos ultimos 12 meses
    meses_12m_distintos = set()
    for a in proventos_por_ativo:
        for p in proventos_por_ativo_dict.get(a["ticker"], []):
            if p["data"] >= data_12m:
                meses_12m_distintos.add(p["data"].strftime("%Y-%m"))
    num_meses_12m = max(1, len(meses_12m_distintos))
    media_mensal_12m = round(total_12m / num_meses_12m, 2)

    # Yield on cost da carteira
    if custo_total_carteira > 0:
        yield_on_cost_carteira = round((total_12m / custo_total_carteira) * 100, 2)
    else:
        yield_on_cost_carteira = 0.0

    # Melhor mes (dos ultimos 12 meses)
    melhor_mes = ""
    melhor_mes_valor = 0.0
    for pm_data in proventos_por_mes:
        if pm_data["mes"] >= data_12m.strftime("%Y-%m"):
            if pm_data["total"] > melhor_mes_valor:
                melhor_mes_valor = pm_data["total"]
                melhor_mes = pm_data["mes"]

    # Projecao do proximo mes
    projecao_proximo_mes = _calcular_projecao(proventos_por_ativo_dict, posicoes)

    tickers_com_proventos = len(proventos_por_ativo_dict)

    resumo = {
        "total_12m": total_12m,
        "media_mensal_12m": media_mensal_12m,
        "yield_on_cost_carteira": yield_on_cost_carteira,
        "melhor_mes": melhor_mes,
        "melhor_mes_valor": round(melhor_mes_valor, 2),
        "projecao_proximo_mes": projecao_proximo_mes,
        "tickers_com_proventos": tickers_com_proventos,
        "total_registros": total_registros,
        "custo_total_carteira": round(custo_total_carteira, 2),
    }

    return {
        "proventos_por_mes": proventos_por_mes,
        "proventos_por_ativo": proventos_por_ativo,
        "resumo": resumo,
    }


def _calcular_projecao(proventos_por_ativo_dict: dict, posicoes: dict) -> float:
    """
    Projeta o valor do proximo mes baseado na media dos ultimos 3 pagamentos
    de cada ativo.

    Para cada ativo com historico de proventos, pega a media dos ultimos 3
    pagamentos (ou menos se houver menos de 3) e soma as projecoes.
    """
    projecao_total = 0.0

    for ticker, pagamentos in proventos_por_ativo_dict.items():
        if ticker not in posicoes:
            continue

        pagamentos_ordenados = sorted(pagamentos, key=lambda x: x["data"])

        # Pega os ultimos 3 pagamentos (ou menos)
        ultimos = pagamentos_ordenados[-3:]

        if not ultimos:
            continue

        # Media dos ultimos pagamentos
        media = sum(p["valor_total"] for p in ultimos) / len(ultimos)

        projecao_total += media

    return round(projecao_total, 2)


# ---------------------------------------------------------------------------
# Funcao 2: grafico_evolucao_proventos()
# ---------------------------------------------------------------------------

def grafico_evolucao_proventos(proventos_por_mes: list, path: str) -> str:
    """
    Gera grafico de barras com a evolucao dos proventos mensais e linha
    de media movel de 3 meses.

    Args:
        proventos_por_mes: lista de dicts {mes, total, tickers}
        path: caminho para salvar o PNG (ex: /tmp/evolucao_proventos.png)

    Returns:
        str: caminho do arquivo gerado
    """
    if not proventos_por_mes:
        # Gera grafico vazio
        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.text(0.5, 0.5, "Sem dados de proventos", ha="center", va="center",
                transform=ax.transAxes, color=COR["muted"], fontsize=12)
        ax.set_title("Evolucao dos Proventos Mensais", fontsize=13, fontweight="bold",
                     color=COR["text"])
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    meses = [p["mes"] for p in proventos_por_mes]
    totais = [p["total"] for p in proventos_por_mes]

    # Labels reduzidos: MM/AA
    labels = []
    for m in meses:
        ano = m[2:4]  # dois digitos do ano
        mes_num = m[5:7]
        labels.append(f"{mes_num}/{ano}")

    # Media movel de 3 meses
    media_movel = []
    for i in range(len(totais)):
        if i >= 2:
            mm3 = sum(totais[i-2:i+1]) / 3
        elif i >= 1:
            mm3 = sum(totais[i-1:i+1]) / 2
        else:
            mm3 = totais[i]
        media_movel.append(mm3)

    fig, ax = plt.subplots(figsize=(10, 4.5))

    x = range(len(meses))

    # Barras
    bars = ax.bar(x, totais, color=COR["green"], alpha=0.55, label="Proventos", zorder=2, width=0.65)

    # Linha de media movel
    ax.plot(x, media_movel, color=COR["accent"], linewidth=2, marker="o",
            markersize=4, label="Media 3 meses", zorder=3)

    # Anotacoes de valor nas barras (apenas barras significativas)
    max_val = max(totais) if totais else 1
    for i, val in enumerate(totais):
        if val > max_val * 0.15:  # Mostra apenas valores acima de 15% do maximo
            ax.text(i, val + max_val * 0.02, f"R${val:,.0f}",
                    ha="center", va="bottom", fontsize=7, color=COR["text"])

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_title("Evolucao dos Proventos Mensais", fontsize=13, fontweight="bold",
                 color=COR["text"])
    ax.set_ylabel("Total Recebido (R$)", fontsize=10, color=COR["muted"])
    ax.legend(frameon=True, fontsize=8, loc="upper left")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v:,.0f}"))
    ax.grid(axis="y", alpha=0.4, linewidth=0.5)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return path


# ---------------------------------------------------------------------------
# Funcao 3: grafico_yield_on_cost()
# ---------------------------------------------------------------------------

def grafico_yield_on_cost(proventos_por_ativo: list, path: str) -> str:
    """
    Gera grafico de barras horizontais com os top 15 ativos por yield on cost.

    FIIs = azul, Acoes = verde.

    Args:
        proventos_por_ativo: lista de dicts de proventos_por_ativo
        path: caminho para salvar o PNG

    Returns:
        str: caminho do arquivo gerado
    """
    if not proventos_por_ativo:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "Sem dados de proventos", ha="center", va="center",
                transform=ax.transAxes, color=COR["muted"], fontsize=12)
        ax.set_title("Dividend Yield on Cost por Ativo", fontsize=13, fontweight="bold",
                     color=COR["text"])
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    # Top 15 por yield on cost
    top = proventos_por_ativo[:15]
    # Inverte para barra horizontal (do topo para baixo)
    top_reversed = list(reversed(top))

    tickers = [f"{a['ticker']}" for a in top_reversed]
    yocs = [a["yield_on_cost"] for a in top_reversed]
    tipos = [a["tipo"] for a in top_reversed]

    # Cores: FII = azul, ACAO = verde
    cores = []
    for t in tipos:
        if t == "FII":
            cores.append(COR["accent"])  # azul
        else:
            cores.append(COR["green"])  # verde

    fig, ax = plt.subplots(figsize=(10, 5.5))

    y_pos = range(len(tickers))
    bars = ax.barh(y_pos, yocs, color=cores, alpha=0.75, height=0.6, zorder=2)

    # Labels de valor
    for i, (ticker, yoc) in enumerate(zip(tickers, yocs)):
        ax.text(yoc + max(yocs) * 0.01, i, f"{yoc:.1f}%",
                va="center", fontsize=8, color=COR["text"])

    ax.set_yticks(y_pos)
    ax.set_yticklabels(tickers, fontsize=8, fontfamily="monospace")
    ax.set_xlabel("Yield on Cost (%)", fontsize=10, color=COR["muted"])
    ax.set_title("Dividend Yield on Cost por Ativo (Top 15)", fontsize=13,
                 fontweight="bold", color=COR["text"])
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.grid(axis="x", alpha=0.4, linewidth=0.5)
    ax.set_axisbelow(True)

    # Legenda de cores
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COR["accent"], alpha=0.75, label="FIIs"),
        Patch(facecolor=COR["green"], alpha=0.75, label="Acoes"),
    ]
    ax.legend(handles=legend_elements, frameon=True, fontsize=8, loc="lower right")

    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return path


# ---------------------------------------------------------------------------
# Funcao 4: renda_passiva_para_pdf()
# ---------------------------------------------------------------------------

def renda_passiva_para_pdf(data: dict, graficos_paths: dict = None) -> list:
    """
    Gera uma lista de flowables do ReportLab para a secao de Renda Passiva.

    Args:
        data: dicionario retornado por compute_renda_passiva()
        graficos_paths: dict opcional com {"evolucao": path, "yoc": path}
                        Se nao informado, assume paths padrao em /tmp/

    Returns:
        Lista de flowables (Paragraph, Spacer, Table, Image) para o PDF.
    """
    if graficos_paths is None:
        graficos_paths = {
            "evolucao": "/tmp/renda_passiva_evolucao.png",
            "yoc": "/tmp/renda_passiva_yoc.png",
        }

    # --- Estilos ---
    h1 = ParagraphStyle(
        "RPH1", fontSize=16, textColor=COR["text"],
        spaceBefore=10, spaceAfter=6, fontName="Helvetica-Bold",
    )
    h2 = ParagraphStyle(
        "RPH2", fontSize=12, textColor=COR["accent"],
        spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold",
    )
    body = ParagraphStyle(
        "RPBody", fontSize=9, textColor=COR["text"],
        leading=14, fontName="Helvetica",
    )
    small = ParagraphStyle(
        "RPSmall", fontSize=8, textColor=COR["muted"],
        leading=11, fontName="Helvetica",
    )
    muted = ParagraphStyle(
        "RPMuted", fontSize=8, textColor=COR["muted"],
        fontName="Helvetica-Oblique",
    )

    story = []
    resumo = data["resumo"]
    proventos_por_ativo = data["proventos_por_ativo"]

    # --- 1. Titulo ---
    story.append(Paragraph("Renda Passiva e Proventos", h1))
    story.append(Paragraph(
        "Analise dos proventos recebidos (dividendos, JCP e rendimentos de FIIs). "
        "O <b>Dividend Yield on Cost</b> mede o retorno em proventos sobre o "
        "<b>custo de aquisicao</b> (preco medio pago), nao sobre o preco atual.",
        body,
    ))
    story.append(Spacer(1, 6))

    # --- 2. Metricas de Resumo ---
    story.append(Paragraph("Resumo", h2))

    metricas_html = (
        f"<b>Total recebido (12 meses):</b> "
        f'<font color="{COR["green"]}"><b>{_fmt_reais(resumo["total_12m"])}</b></font><br/>'
        f"<b>Media mensal (12 meses):</b> "
        f'<font color="{COR["green"]}"><b>{_fmt_reais(resumo["media_mensal_12m"])}</b></font><br/>'
        f"<b>Dividend Yield on Cost da Carteira:</b> "
        f'<font color="{COR["accent"]}"><b>{resumo["yield_on_cost_carteira"]:.2f}%</b></font><br/>'
        f"<b>Melhor mes:</b> {resumo['melhor_mes']} "
        f'({_fmt_reais(resumo["melhor_mes_valor"])})<br/>'
        f"<b>Projecao proximo mes:</b> "
        f'<font color="{COR["purple"]}"><b>{_fmt_reais(resumo["projecao_proximo_mes"])}</b></font><br/>'
        f"<b>Ativos com proventos:</b> {resumo['tickers_com_proventos']} | "
        f"<b>Total de registros:</b> {resumo['total_registros']}"
    )
    story.append(Paragraph(metricas_html, body))
    story.append(Spacer(1, 8))

    # --- 3. Grafico de evolucao mensal ---
    evolucao_path = graficos_paths.get("evolucao", "/tmp/renda_passiva_evolucao.png")
    if os.path.exists(evolucao_path):
        story.append(Paragraph("Evolucao dos Proventos", h2))
        img = Image(evolucao_path, width=170 * mm, height=80 * mm)
        story.append(img)
        story.append(Spacer(1, 6))

    # --- 4. Tabela Top 10 ativos por yield on cost ---
    story.append(Paragraph("Top 10 Ativos por Yield on Cost", h2))
    story.append(Paragraph(
        "Rentabilidade passiva sobre o custo de aquisicao. "
        "Quanto cada ativo devolveu em proventos nos ultimos 12 meses.",
        muted,
    ))
    story.append(Spacer(1, 3))

    top10 = proventos_por_ativo[:10]

    t_header = ["Ativo", "Tipo", "Qtd", "Proventos 12m", "Yield on Cost", "Ult. Prov.", "Freq."]
    t_data = [t_header]

    for a in top10:
        tipo_label = a["tipo"]
        yoc_color = COR["green"] if a["yield_on_cost"] > 0 else COR["muted"]
        t_data.append([
            Paragraph(f"<b>{a['ticker']}</b>", small),
            Paragraph(tipo_label, small),
            Paragraph(f"{a['qtd']:.0f}", small),
            Paragraph(_fmt_reais(a["proventos_12m"]), small),
            Paragraph(
                f'<font color="{yoc_color}"><b>{a["yield_on_cost"]:.2f}%</b></font>',
                small,
            ),
            Paragraph(_fmt_reais(a["ultimo_provento"]), small),
            Paragraph(f"{a['frequencia_meses']}m" if a['frequencia_meses'] > 1 else "Mensal", small),
        ])

    col_w = [22*mm, 16*mm, 12*mm, 28*mm, 28*mm, 28*mm, 14*mm]
    t = Table(t_data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COR["accent"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), COR["white"]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, COR["border"]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    # --- 5. Grafico de yield on cost ---
    yoc_path = graficos_paths.get("yoc", "/tmp/renda_passiva_yoc.png")
    if os.path.exists(yoc_path):
        story.append(Paragraph("Yield on Cost por Ativo", h2))
        img = Image(yoc_path, width=170 * mm, height=90 * mm)
        story.append(img)
        story.append(Spacer(1, 6))

    # --- 6. Paragrafo de projecao ---
    story.append(Paragraph("Projecao de Renda Passiva", h2))
    proj = resumo["projecao_proximo_mes"]
    media = resumo["media_mensal_12m"]
    story.append(Paragraph(
        f"Com base na media dos ultimos 3 pagamentos de cada ativo, a "
        f"<b>projecao para o proximo mes</b> e de "
        f'<font color="{COR["purple"]}"><b>{_fmt_reais(proj)}</b></font>. '
        f"A media historica dos ultimos 12 meses foi de "
        f'<font color="{COR["green"]}"><b>{_fmt_reais(media)}</b></font>/mes.',
        body,
    ))

    return story


# ---------------------------------------------------------------------------
# Funcao 5: resumo_renda_passiva_telegram()
# ---------------------------------------------------------------------------

def resumo_renda_passiva_telegram(data: dict) -> str:
    """
    Gera texto curto (max ~300 caracteres) para Telegram com metricas
    principais de renda passiva.

    Args:
        data: dicionario retornado por compute_renda_passiva()

    Returns:
        str: texto formatado para Telegram
    """
    resumo = data["resumo"]

    linha1 = (
        f"💰 Proventos 12m: {_fmt_reais(resumo['total_12m'])} "
        f"| Media: {_fmt_reais(resumo['media_mensal_12m'])}/mes"
    )
    linha2 = (
        f"📊 Yield on Cost: {resumo['yield_on_cost_carteira']:.1f}% "
        f"| Proj. prox: {_fmt_reais(resumo['projecao_proximo_mes'])}"
    )
    linha3 = (
        f"🏆 Melhor mes: {resumo['melhor_mes']} "
        f"({_fmt_reais(resumo['melhor_mes_valor'])}) "
        f"| {resumo['tickers_com_proventos']} ativos"
    )

    return f"{linha1}\n{linha2}\n{linha3}"


# ---------------------------------------------------------------------------
# Teste rapido (executado apenas quando o modulo e rodado diretamente)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  MODULO RENDA PASSIVA — Teste")
    print("=" * 60)

    # 1. Computar dados
    print("\n[1] Consultando banco de dados...")
    data = compute_renda_passiva()

    # 2. Exibir resumo
    print("\n[2] Resumo:")
    r = data["resumo"]
    print(f"    Total 12 meses:              {_fmt_reais(r['total_12m'])}")
    print(f"    Media mensal 12m:            {_fmt_reais(r['media_mensal_12m'])}")
    print(f"    Yield on Cost carteira:      {r['yield_on_cost_carteira']:.2f}%")
    print(f"    Melhor mes:                  {r['melhor_mes']} ({_fmt_reais(r['melhor_mes_valor'])})")
    print(f"    Projecao proximo mes:        {_fmt_reais(r['projecao_proximo_mes'])}")
    print(f"    Tickers com proventos:       {r['tickers_com_proventos']}")
    print(f"    Total registros:             {r['total_registros']}")
    print(f"    Custo total carteira:        {_fmt_reais(r['custo_total_carteira'])}")

    # 3. Proventos por mes
    print(f"\n[3] Proventos por mes ({len(data['proventos_por_mes'])} meses):")
    for pm in data["proventos_por_mes"]:
        print(f"    {pm['mes']}: {_fmt_reais(pm['total'])} ({len(pm['tickers'])} tickers)")

    # 4. Top 10 ativos por yield on cost
    print(f"\n[4] Top 10 ativos por Yield on Cost ({len(data['proventos_por_ativo'])} total):")
    for i, a in enumerate(data["proventos_por_ativo"][:10]):
        print(f"    {i+1}. {a['ticker']:7s} ({a['tipo']:5s}) "
              f"qtd={a['qtd']:6.0f} pm=R${a['pm']:.2f} "
              f"prov12m={_fmt_reais(a['proventos_12m'])} "
              f"YoC={a['yield_on_cost']:.2f}% "
              f"freq={a['frequencia_meses']}m")

    # 5. Gerar graficos
    print("\n[5] Gerando graficos...")
    path_evol = grafico_evolucao_proventos(data["proventos_por_mes"], "/tmp/test_renda_passiva_evolucao.png")
    print(f"    Grafico evolucao: {path_evol}")

    path_yoc = grafico_yield_on_cost(data["proventos_por_ativo"], "/tmp/test_renda_passiva_yoc.png")
    print(f"    Grafico YoC:      {path_yoc}")

    # 6. Telegram
    print("\n[6] Resumo Telegram:")
    print(resumo_renda_passiva_telegram(data))

    # 7. PDF flowables
    graficos = {"evolucao": path_evol, "yoc": path_yoc}
    flowables = renda_passiva_para_pdf(data, graficos)
    print(f"\n[7] PDF flowables gerados: {len(flowables)} elementos")

    print("\n✅ Teste concluido com sucesso!")