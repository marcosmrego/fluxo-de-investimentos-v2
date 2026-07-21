#!/usr/bin/env python3
"""
Modulo Fundamentalista — Indicadores ampliados da carteira
============================================================
Coleta indicadores fundamentalistas do Fundamentus (22 ações + 16 FIIs),
gera ranking, gráficos comparativos e tabelas para PDF.

Integração: importado por relatorio_executivo.py ou usado standalone.
Autor: Hermes AI Agent
Data: 2026-07-20
"""

import os
import sys
import tempfile
from datetime import date

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import psycopg2

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Image, Table, TableStyle, PageBreak

# ═══════════════════════════════════════════════════════════════════
# Configurações
# ═══════════════════════════════════════════════════════════════════

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_utils import DB_CONFIG

# Tema CLEAN
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

PALETA_BARRAS = ["#0969DA", "#1A7F37", "#CF222E", "#8250DF", "#BC4C00",
                 "#9A6700", "#0550AE", "#116329", "#A40E26", "#5E39A4"]


# ═══════════════════════════════════════════════════════════════════
# Dados
# ═══════════════════════════════════════════════════════════════════

def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn


def compute() -> dict:
    """Coleta indicadores fundamentalistas mais recentes do banco."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT f.*, a.nome, a.setor
        FROM investimentos.indicadores_fundamentalistas_v2 f
        JOIN investimentos.ativos a ON a.ticker = f.ticker
        WHERE f.data_coleta = (
            SELECT MAX(data_coleta) FROM investimentos.indicadores_fundamentalistas_v2
        )
        ORDER BY a.tipo, f.ticker
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    acoes = []
    fiis = []
    for r in rows:
        d = dict(r)
        if d.get("tipo") == "ACAO":
            acoes.append(d)
        elif d.get("tipo") == "FII":
            fiis.append(d)

    return {
        "acoes": acoes,
        "fiis": fiis,
        "total": len(rows),
        "data_coleta": rows[0]["data_coleta"].isoformat() if rows else str(date.today()),
    }


# ═══════════════════════════════════════════════════════════════════
# Gráficos
# ═══════════════════════════════════════════════════════════════════

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "figure.dpi": 120,
    "savefig.dpi": 120,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def grafico_roe(acoes: list[dict], output_path: str) -> str:
    """Gráfico de barras: ROE por ação (top 16)."""
    dados = [(a["ticker"], a.get("roe")) for a in acoes if a.get("roe") is not None]
    dados.sort(key=lambda x: x[1], reverse=True)

    tickers = [d[0] for d in dados]
    valores = [d[1] for d in dados]
    cores = [COR["green"] if v >= 15 else COR["accent"] if v >= 10 else COR["orange"]
             for v in valores]

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars = ax.barh(range(len(tickers)), valores, color=cores, height=0.6)
    ax.set_yticks(range(len(tickers)))
    ax.set_yticklabels(tickers, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("ROE (%)", fontsize=9)
    ax.set_title("ROE — Retorno sobre Patrimônio Líquido", fontsize=12, fontweight="bold", color=COR["text"])
    ax.axvline(x=15, color=COR["green"], linestyle="--", linewidth=0.8, alpha=0.5, label="Excelente (>15%)")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(axis="x", alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, valores):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}%", va="center", fontsize=7, color=COR["muted"])

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def grafico_p_vp(acoes: list[dict], output_path: str) -> str:
    """Gráfico de barras: P/VP por ação (menor = mais barato)."""
    dados = [(a["ticker"], a.get("p_vp")) for a in acoes if a.get("p_vp") is not None]
    dados.sort(key=lambda x: x[1])

    tickers = [d[0] for d in dados]
    valores = [d[1] for d in dados]
    cores = [COR["green"] if v <= 1 else COR["accent"] if v <= 3 else COR["orange"]
             for v in valores]

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars = ax.barh(range(len(tickers)), valores, color=cores, height=0.6)
    ax.set_yticks(range(len(tickers)))
    ax.set_yticklabels(tickers, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("P/VP", fontsize=9)
    ax.set_title("P/VP — Preço sobre Valor Patrimonial", fontsize=12, fontweight="bold", color=COR["text"])
    ax.axvline(x=1, color=COR["green"], linestyle="--", linewidth=0.8, alpha=0.5, label="Sub-valorizado (<1)")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(axis="x", alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, valores):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"{v:.2f}", va="center", fontsize=7, color=COR["muted"])

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def grafico_dividend_yield(acoes: list[dict], fiis: list[dict], output_path: str) -> str:
    """Gráfico de barras: Dividend Yield — ações + FIIs."""
    dados = []
    for a in acoes:
        dy = a.get("dividend_yield")
        if dy is not None:
            dados.append((a["ticker"], dy, "Ação"))
    for f in fiis:
        dy = f.get("dividend_yield")
        if dy is not None:
            dados.append((f["ticker"], dy, "FII"))

    dados.sort(key=lambda x: x[1], reverse=True)

    tickers = [f"{d[0]}" for d in dados]
    valores = [d[1] for d in dados]
    tipos = [d[2] for d in dados]
    cores = [COR["green"] if t == "FII" else COR["accent"] for t in tipos]

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars = ax.barh(range(len(tickers)), valores, color=cores, height=0.6)
    ax.set_yticks(range(len(tickers)))
    ax.set_yticklabels(tickers, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Dividend Yield (%)", fontsize=9)
    ax.set_title("Dividend Yield — Ações vs FIIs", fontsize=12, fontweight="bold", color=COR["text"])

    # Legenda
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COR["green"], label="FII"),
        Patch(facecolor=COR["accent"], label="Ação"),
    ]
    ax.legend(handles=legend_elements, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, valores):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}%", va="center", fontsize=7, color=COR["muted"])

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def grafico_ev_ebitda(acoes: list[dict], output_path: str) -> str:
    """Gráfico de barras: EV/EBITDA por ação."""
    dados = [(a["ticker"], a.get("ev_ebitda")) for a in acoes if a.get("ev_ebitda") is not None]
    dados.sort(key=lambda x: x[1])

    tickers = [d[0] for d in dados]
    valores = [d[1] for d in dados]
    cores = [COR["green"] if v <= 6 else COR["accent"] if v <= 12 else COR["orange"]
             for v in valores]

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bars = ax.barh(range(len(tickers)), valores, color=cores, height=0.6)
    ax.set_yticks(range(len(tickers)))
    ax.set_yticklabels(tickers, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("EV/EBITDA", fontsize=9)
    ax.set_title("EV/EBITDA — Valor da Firma sobre EBITDA", fontsize=12, fontweight="bold", color=COR["text"])
    ax.axvline(x=6, color=COR["green"], linestyle="--", linewidth=0.8, alpha=0.5, label="Barato (<6x)")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(axis="x", alpha=0.3, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    for bar, v in zip(bars, valores):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}x", va="center", fontsize=7, color=COR["muted"])

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


# ═══════════════════════════════════════════════════════════════════
# Formatadores PDF
# ═══════════════════════════════════════════════════════════════════

STYLE_TITLE = ParagraphStyle("fund_title", fontSize=14, fontName="Helvetica-Bold",
                              textColor=COR["text"], spaceAfter=6 * mm)
STYLE_SUBTITLE = ParagraphStyle("fund_subtitle", fontSize=10, fontName="Helvetica",
                                 textColor=COR["muted"], spaceAfter=4 * mm)
STYLE_CELL = ParagraphStyle("fund_cell", fontSize=7, fontName="Helvetica",
                             textColor=COR["text"], leading=9)
STYLE_CELL_BOLD = ParagraphStyle("fund_cell_bold", fontSize=7, fontName="Helvetica-Bold",
                                  textColor=COR["text"], leading=9)
STYLE_CELL_GREEN = ParagraphStyle("fund_cell_green", fontSize=7, fontName="Helvetica-Bold",
                                   textColor=COR["green"], leading=9)
STYLE_CELL_RED = ParagraphStyle("fund_cell_red", fontSize=7, fontName="Helvetica-Bold",
                                 textColor=COR["red"], leading=9)
STYLE_CELL_HEADER = ParagraphStyle("fund_hdr", fontSize=7, fontName="Helvetica-Bold",
                                    textColor="white", leading=9)


def _p(text, style=STYLE_CELL):
    return Paragraph(text, style)


def _ranking_acoes_tabela(acoes: list[dict]) -> list:
    """Tabela de ranking de ações com principais indicadores."""
    header = [_p("Ticker", STYLE_CELL_HEADER),
              _p("Setor", STYLE_CELL_HEADER),
              _p("P/L", STYLE_CELL_HEADER),
              _p("P/VP", STYLE_CELL_HEADER),
              _p("ROE %", STYLE_CELL_HEADER),
              _p("DY %", STYLE_CELL_HEADER),
              _p("EV/EBITDA", STYLE_CELL_HEADER),
              _p("Marg.Liq %", STYLE_CELL_HEADER),
              _p("Div.Liq/PL", STYLE_CELL_HEADER),
              _p("Cresc.5a", STYLE_CELL_HEADER)]

    data = [header]
    for a in sorted(acoes, key=lambda x: x.get("roe") or 0, reverse=True):
        setor = (a.get("setor") or "")[:18]
        row = [
            _p(a["ticker"], STYLE_CELL_BOLD),
            _p(setor, STYLE_CELL),
            _p(f"{a['p_l']:.1f}" if a.get("p_l") else "—", STYLE_CELL),
            _p(f"{a['p_vp']:.2f}" if a.get("p_vp") else "—",
               STYLE_CELL_GREEN if (a.get("p_vp") or 99) <= 1 else STYLE_CELL),
            _p(f"{a['roe']:.1f}" if a.get("roe") else "—",
               STYLE_CELL_GREEN if (a.get("roe") or 0) >= 15 else STYLE_CELL),
            _p(f"{a['dividend_yield']:.1f}" if a.get("dividend_yield") else "—", STYLE_CELL),
            _p(f"{a['ev_ebitda']:.1f}" if a.get("ev_ebitda") else "—", STYLE_CELL),
            _p(f"{a['marg_liquida']:.1f}" if a.get("marg_liquida") else "—", STYLE_CELL),
            _p(f"{a['div_liq_patrim']:.2f}" if a.get("div_liq_patrim") else "—",
               STYLE_CELL_GREEN if (a.get("div_liq_patrim") or 99) <= 0 else STYLE_CELL),
            _p(f"{a['cres_rec_5a']:.1f}" if a.get("cres_rec_5a") else "—", STYLE_CELL),
        ]
        data.append(row)

    col_widths = [16 * mm, 28 * mm, 10 * mm, 10 * mm, 10 * mm,
                  9 * mm, 14 * mm, 12 * mm, 14 * mm, 12 * mm]

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(COR["accent"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        # Body
        ("BACKGROUND", (0, 1), (-1, -1), HexColor(COR["card"])),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(COR["card"]), HexColor(COR["bg"])]),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor(COR["border"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [tbl, Spacer(1, 3 * mm)]


def _ranking_fiis_tabela(fiis: list[dict]) -> list:
    """Tabela de ranking de FIIs com principais indicadores."""
    header = [_p("Ticker", STYLE_CELL_HEADER),
              _p("P/VP", STYLE_CELL_HEADER),
              _p("VP/Cota", STYLE_CELL_HEADER),
              _p("DY %", STYLE_CELL_HEADER),
              _p("FFO Yield %", STYLE_CELL_HEADER),
              _p("FFO/Cota", STYLE_CELL_HEADER),
              _p("Receita 12m", STYLE_CELL_HEADER),
              _p("Patrim.Liq", STYLE_CELL_HEADER)]

    data = [header]
    for f in sorted(fiis, key=lambda x: x.get("dividend_yield") or 0, reverse=True):
        row = [
            _p(f["ticker"], STYLE_CELL_BOLD),
            _p(f"{f['p_vp']:.2f}" if f.get("p_vp") else "—",
               STYLE_CELL_GREEN if (f.get("p_vp") or 99) <= 1 else STYLE_CELL),
            _p(f"R$ {f['vp_cota']:.0f}" if f.get("vp_cota") else "—", STYLE_CELL),
            _p(f"{f['dividend_yield']:.1f}" if f.get("dividend_yield") else "—",
               STYLE_CELL_GREEN if (f.get("dividend_yield") or 0) >= 8 else STYLE_CELL),
            _p(f"{f['ffo_yield']:.1f}" if f.get("ffo_yield") else "—", STYLE_CELL),
            _p(f"R$ {f['ffo_cota']:.1f}" if f.get("ffo_cota") else "—", STYLE_CELL),
            _p(_fmt_money(f.get("receita_12m")), STYLE_CELL),
            _p(_fmt_money(f.get("patrimonio_liquido")), STYLE_CELL),
        ]
        data.append(row)

    col_widths = [14 * mm, 12 * mm, 16 * mm, 11 * mm, 16 * mm, 16 * mm, 22 * mm, 22 * mm]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(COR["green"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -1), HexColor(COR["card"])),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor(COR["card"]), HexColor(COR["bg"])]),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor(COR["border"])),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [tbl, Spacer(1, 3 * mm)]


def _fmt_money(val) -> str:
    """Formata valor monetário para exibição compacta."""
    if val is None:
        return "—"
    v = float(val)
    if abs(v) >= 1_000_000_000:
        return f"R$ {v/1e9:.2f}B"
    elif abs(v) >= 1_000_000:
        return f"R$ {v/1e6:.1f}M"
    elif abs(v) >= 1_000:
        return f"R$ {v/1e3:.1f}K"
    else:
        return f"R$ {v:.0f}"


def _resumo_metricas(data: dict) -> list:
    """Parágrafo de resumo com destaques fundamentalistas."""
    acoes = data["acoes"]
    fiis = data["fiis"]

    # Melhor ROE
    acoes_roe = [(a["ticker"], a["roe"]) for a in acoes if a.get("roe")]
    acoes_roe.sort(key=lambda x: x[1], reverse=True)
    top_roe = acoes_roe[:3] if acoes_roe else []

    # Melhor P/VP
    acoes_pvp = [(a["ticker"], a["p_vp"]) for a in acoes if a.get("p_vp")]
    acoes_pvp.sort(key=lambda x: x[1])
    top_pvp = acoes_pvp[:3] if acoes_pvp else []

    # Melhor DY
    fiis_dy = [(f["ticker"], f["dividend_yield"]) for f in fiis if f.get("dividend_yield")]
    fiis_dy.sort(key=lambda x: x[1], reverse=True)
    top_dy = fiis_dy[:3] if fiis_dy else []

    lines = [
        Paragraph("📊 RESUMO FUNDAMENTALISTA", STYLE_TITLE),
        Spacer(1, 2 * mm),
    ]

    if top_roe:
        items = ", ".join(f"<b>{t}</b> ({v:.1f}%)" for t, v in top_roe)
        lines.append(Paragraph(f"🏆 <b>Maiores ROE:</b> {items}", STYLE_SUBTITLE))

    if top_pvp:
        items = ", ".join(f"<b>{t}</b> (P/VP={v:.2f})" for t, v in top_pvp)
        lines.append(Paragraph(f"💎 <b>Mais descontados (P/VP):</b> {items}", STYLE_SUBTITLE))

    if top_dy:
        items = ", ".join(f"<b>{t}</b> ({v:.1f}%)" for t, v in top_dy)
        lines.append(Paragraph(f"💰 <b>Maiores Dividend Yield:</b> {items}", STYLE_SUBTITLE))

    # Média ROE
    all_roe = [v for _, v in acoes_roe]
    if all_roe:
        media_roe = sum(all_roe) / len(all_roe)
        lines.append(Paragraph(
            f"📈 <b>ROE Médio da Carteira:</b> {media_roe:.1f}% "
            f"({'SAUDÁVEL (>15%)' if media_roe >= 15 else 'REGULAR (10-15%)' if media_roe >= 10 else 'BAIXO (<10%)'})",
            STYLE_SUBTITLE))

    lines.append(Spacer(1, 4 * mm))
    return lines


def fundamentalista_para_pdf(data: dict, graficos_paths: dict) -> list:
    """Retorna lista de flowables (Paragraph, Table, Image, Spacer) para o PDF."""
    story = []

    # ── Resumo ──
    story.extend(_resumo_metricas(data))

    # ── Tabela Ações ──
    story.append(Paragraph("📋 Ranking de Ações", STYLE_TITLE))
    story.append(Spacer(1, 2 * mm))
    story.extend(_ranking_acoes_tabela(data["acoes"]))
    story.append(Spacer(1, 2 * mm))

    # ── Gráficos Ações ──
    graficos_acoes = []
    for key in ["f_roe", "f_pvp", "f_ev_ebitda"]:
        if key in graficos_paths:
            graficos_acoes.append(Image(graficos_paths[key], width=175 * mm, height=97 * mm))
            graficos_acoes.append(Spacer(1, 3 * mm))

    for g in graficos_acoes:
        story.append(g)

    # ── Tabela FIIs ──
    if data["fiis"]:
        story.append(PageBreak())
        story.append(Paragraph("📋 Ranking de FIIs", STYLE_TITLE))
        story.append(Spacer(1, 2 * mm))
        story.extend(_ranking_fiis_tabela(data["fiis"]))
        story.append(Spacer(1, 2 * mm))

    # ── Gráfico Dividend Yield ──
    if "f_dy" in graficos_paths:
        story.append(Image(graficos_paths["f_dy"], width=175 * mm, height=105 * mm))

    return story


# ═══════════════════════════════════════════════════════════════════
# Standalone
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import psycopg2.extras

    print("=" * 60)
    print("  MÓDULO FUNDAMENTALISTA — TESTE STANDALONE")
    print("=" * 60)

    # Passo 1: Coletar dados
    print("\n[1/3] Coletando indicadores do banco...")
    data = compute()
    print(f"  Data coleta: {data['data_coleta']}")
    print(f"  Total ativos: {data['total']}")
    print(f"  Ações: {len(data['acoes'])}")
    print(f"  FIIs: {len(data['fiis'])}")

    # Exibe top 5 ROE
    acoes_roe = [(a["ticker"], a.get("roe")) for a in data["acoes"] if a.get("roe")]
    acoes_roe.sort(key=lambda x: x[1], reverse=True)
    print(f"\n  Top 5 ROE:")
    for t, v in acoes_roe[:5]:
        print(f"    {t:8s}  ROE={v:.1f}%")

    # Passo 2: Gerar gráficos
    print("\n[2/3] Gerando gráficos...")
    tmp = tempfile.mkdtemp(prefix="fund_")

    g_roe = grafico_roe(data["acoes"], os.path.join(tmp, "roe.png"))
    print(f"  ROE → {g_roe}")
    g_pvp = grafico_p_vp(data["acoes"], os.path.join(tmp, "pvp.png"))
    print(f"  P/VP → {g_pvp}")
    g_dy = grafico_dividend_yield(data["acoes"], data["fiis"], os.path.join(tmp, "dy.png"))
    print(f"  DY → {g_dy}")
    g_ev = grafico_ev_ebitda(data["acoes"], os.path.join(tmp, "ev_ebitda.png"))
    print(f"  EV/EBITDA → {g_ev}")

    # Passo 3: Testar PDF
    print("\n[3/3] Testando formatador PDF...")
    paths = {"f_roe": g_roe, "f_pvp": g_pvp, "f_dy": g_dy, "f_ev_ebitda": g_ev}
    story = fundamentalista_para_pdf(data, paths)
    print(f"  Flowables gerados: {len(story)} elementos")
    types = set(type(f).__name__ for f in story)
    print(f"  Tipos: {', '.join(sorted(types))}")

    print("\n" + "=" * 60)
    print("  TESTE CONCLUIDO COM SUCESSO")
    print(f"  Gráficos em: {tmp}")
    print("=" * 60)