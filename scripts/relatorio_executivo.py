#!/usr/bin/env python3
"""
Relatorio Executivo da Carteira — Prof. Marcos
Tema CLEAN (claro) — Graficos profissionais com matplotlib + PDF via reportlab.
"""

import os, sys, io, json, uuid, tempfile, datetime, re
import psycopg2

# -- Modulos de analises avancadas --
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'relatorio_modulos'))
import modulo_alocacao_ir
import modulo_alertas_inteligentes
import modulo_tributario
import modulo_setorial
import modulo_renda_passiva
import modulo_benchmarking
import modulo_risco
import modulo_fundamentalista
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                 Table, TableStyle, PageBreak, KeepTogether)
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from db_utils import DB_CONFIG
DRIVE_FOLDER_ID = "1Qn8_wi0rsL16gPgI8dVHpoefjBV6GuqL"
OUT_DIR = "/opt/data/fluxo-de-investimentos-v2/reports"
os.makedirs(OUT_DIR, exist_ok=True)
TMPDIR = tempfile.mkdtemp(prefix="relatorio_")

# ── Estilo CLEAN ────────────────────────────────────────────────
COR = {
    "bg":       "#FAFBFC",
    "card":     "#FFFFFF",
    "border":   "#D0D7DE",
    "text":     "#1F2328",
    "muted":    "#656D76",
    "accent":   "#0969DA",
    "green":    "#1A7F37",
    "red":      "#CF222E",
    "yellow":   "#9A6700",
    "orange":   "#BC4C00",
    "purple":   "#8250DF",
    "white":    "#FFFFFF",
}
PALETA = ["#0969DA", "#1A7F37", "#CF222E", "#9A6700", "#8250DF",
          "#BC4C00", "#54AEFF", "#4AC26B", "#F77882", "#D4A72C"]

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

# ── Dados ───────────────────────────────────────────────────────
def get_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.ticker, p.quantidade_total, p.preco_medio, p.custo_total,
               c.fechamento as preco_atual,
               ROUND((c.fechamento - p.preco_medio) * p.quantidade_total, 2) as lucro,
               ROUND(((c.fechamento / p.preco_medio) - 1) * 100, 2) as rent_pct,
               a.nome, a.tipo, a.setor
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        LEFT JOIN LATERAL (
            SELECT fechamento FROM investimentos.cotacoes 
            WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
        ) c ON true
        WHERE p.quantidade_total > 0
        ORDER BY p.custo_total DESC
    """)
    posicoes = []
    for r in cur.fetchall():
        posicoes.append({
            "ticker": r[0], "qtd": float(r[1]), "pm": float(r[2]), "custo": float(r[3]),
            "preco": float(r[4]) if r[4] else 0, "lucro": float(r[5]) if r[5] else 0,
            "rent": float(r[6]) if r[6] else 0, "nome": r[7], "tipo": r[8], "setor": r[9] or "",
        })
    
    custo_total = sum(p["custo"] for p in posicoes)
    mercado_total = sum(p["preco"] * p["qtd"] for p in posicoes if p["preco"])
    rent_total = ((mercado_total / custo_total) - 1) * 100 if custo_total else 0
    
    # Aportes
    cur.execute("""
        SELECT TO_CHAR(data_pregao, 'YYYY-MM'),
               SUM(CASE WHEN o.tipo_operacao='COMPRA' THEN o.quantidade*o.preco_unitario ELSE 0 END)
        FROM investimentos.operacoes o
        JOIN investimentos.notas_negociacao n ON n.id = o.nota_id
        WHERE o.ticker IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)
    aportes = [(r[0], float(r[1])) for r in cur.fetchall()]
    
    # Ultimas operacoes
    cur.execute("""
        SELECT n.data_pregao, o.ticker, o.tipo_operacao, o.quantidade, o.preco_unitario
        FROM investimentos.operacoes o
        JOIN investimentos.notas_negociacao n ON n.id = o.nota_id
        WHERE o.ticker IS NOT NULL
        ORDER BY n.data_pregao DESC LIMIT 12
    """)
    ultimas_ops = [(r[0], r[1], r[2], float(r[3]), float(r[4])) for r in cur.fetchall()]
    
    # Alertas
    cur.execute("""
        SELECT ticker, mensagem, data_alerta
        FROM investimentos.alertas
        WHERE data_alerta >= NOW() - INTERVAL '7 days'
        ORDER BY data_alerta DESC LIMIT 10
    """)
    alertas = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    
    # IFIX
    cur.execute("SELECT preco, variacao_percentual FROM investimentos.ifix_snapshot_diario ORDER BY data_referencia DESC LIMIT 1")
    ifix = cur.fetchone()
    
    # Historico 5d para tendencias (por ativo)
    cur.execute("""
        SELECT ticker, data, fechamento, variacao_pct
        FROM investimentos.cotacoes
        WHERE data >= CURRENT_DATE - INTERVAL '10 days'
        ORDER BY ticker, data
    """)
    hist_cot = {}
    for r in cur.fetchall():
        ticker, data, fech, var = r
        if ticker not in hist_cot:
            hist_cot[ticker] = []
        hist_cot[ticker].append({"data": data, "preco": float(fech) if fech else 0, "var": float(var) if var else 0})
    
    conn.close()
    
    # ── Dados de alocacao ──
    aloc = _compute_alocacao(posicoes, custo_total)
    aloc_avancada = modulo_alocacao_ir.compute_alocacao_avancada(posicoes, custo_total)
    
    # ── Dados tributarios ──
    trib = modulo_tributario.compute_situacao_tributaria()
    
    # ── Alertas inteligentes ──
    alertas_int = modulo_alertas_inteligentes.gerar_alertas_inteligentes()
    
    # ── Dados setoriais ──
    setorial = modulo_setorial.compute_analise_setorial()
    
    # ── Renda passiva ──
    renda_passiva = modulo_renda_passiva.compute_renda_passiva()
    
    # ── Benchmarking ──
    benchmarking = modulo_benchmarking.compute_benchmarking()
    
    # ── Risco ──
    risco = modulo_risco.compute_risco()
    fundamentalista = modulo_fundamentalista.compute()
    
    return {
        "posicoes": posicoes,
        "custo_total": custo_total,
        "mercado_total": mercado_total,
        "rent_total": rent_total,
        "aportes": aportes,
        "ultimas_ops": ultimas_ops,
        "alertas": alertas,
        "ifix": ifix,
        "hist_cot": hist_cot,
        "aloc": aloc,
        "aloc_avancada": aloc_avancada,
        "trib": trib,
        "alertas_int": alertas_int,
        "setorial": setorial,
        "renda_passiva": renda_passiva,
        "benchmarking": benchmarking,
        "risco": risco,
        "fundamentalista": fundamentalista,
        "data": datetime.date.today().strftime("%d/%m/%Y"),
    }


# ── Graficos ────────────────────────────────────────────────────
def _compute_alocacao(posicoes, custo_total):
    """Calcula distribuicao atual vs alvo por classe."""
    ALVO = {
        "RENDA_FIXA": ("Renda Fixa", 20.0, "#8250DF"),
        "FII":        ("FIIs",       25.0, "#0969DA"),
        "ACAO":       ("Acoes",      35.0, "#1A7F37"),
        "ETF":        ("ETFs BR",    10.0, "#9A6700"),
        "ETF_INTL":   ("ETF Intl",   10.0, "#BC4C00"),
    }
    atual_map = {}
    for p in posicoes:
        t = p["tipo"]
        if t == "ETF_INTERNACIONAL":
            t = "ETF_INTL"
        elif t == "RENDA_FIXA":
            t = "RENDA_FIXA"
        atual_map[t] = atual_map.get(t, 0) + p["custo"]
    
    rows = []
    for k, (nome, alvo, cor) in ALVO.items():
        atual_val = atual_map.get(k, 0)
        pct_atual = (atual_val / custo_total * 100) if custo_total > 0 else 0
        gap = pct_atual - alvo
        if gap > 10:
            status, emoji = "VENDER", "🔴"
        elif gap > 3:
            status, emoji = "REDUZIR", "🟡"
        elif gap < -10:
            status, emoji = "COMPRAR", "🟢"
        elif gap < -3:
            status, emoji = "AUMENTAR", "🟢"
        else:
            status, emoji = "OK", "✅"
        
        rows.append({
            "classe": nome, "pct_atual": pct_atual, "pct_alvo": alvo,
            "gap": gap, "status": status, "emoji": emoji, "cor": cor,
            "atual_val": atual_val,
        })
    return rows


def grafico_alocacao(aloc, path):
    """Grafico de barras agrupadas: Atual vs Alvo por classe."""
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.set_facecolor(COR["bg"])
    ax.set_facecolor(COR["card"])
    
    classes = [r["classe"] for r in aloc]
    x = np.arange(len(classes))
    w = 0.35
    
    atual_vals = [r["pct_atual"] for r in aloc]
    alvo_vals = [r["pct_alvo"] for r in aloc]
    colors = [r["cor"] for r in aloc]
    
    bars1 = ax.bar(x - w/2, atual_vals, w, label="Atual", color=colors, alpha=0.9, edgecolor="white", linewidth=0.5)
    bars2 = ax.bar(x + w/2, alvo_vals, w, label="Alvo", color=colors, alpha=0.35, edgecolor=colors, linewidth=0.8, hatch="///")
    
    # Anotar gaps
    for i, r in enumerate(aloc):
        gap = r["gap"]
        if abs(gap) > 1:
            y = max(r["pct_atual"], r["pct_alvo"]) + 1.5
            color_gap = COR["green"] if gap < 0 else COR["red"]
            ax.annotate(f"{gap:+.0f}%", (x[i], y), ha="center", fontsize=8,
                       fontweight="bold", color=color_gap)
    
    ax.set_xticks(x)
    ax.set_xticklabels(classes, fontsize=9)
    ax.set_ylabel("% da Carteira", fontsize=9, color=COR["muted"])
    ax.set_title("Alocacao Atual vs Alvo Estrategico", fontsize=12, fontweight="bold", color=COR["text"], pad=15)
    ax.legend(fontsize=9, loc="upper right", frameon=True, facecolor=COR["white"], edgecolor=COR["border"])
    ax.grid(axis="y", alpha=0.3, color=COR["border"])
    ax.set_ylim(0, max(max(atual_vals), max(alvo_vals)) * 1.25)
    
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=COR["bg"], edgecolor="none")
    plt.close(fig)


def grafico_composicao(posicoes, path):
    """Pizza: composicao por classe"""
    classes = {}
    for p in posicoes:
        t = p["tipo"]
        classes[t] = classes.get(t, 0) + p["custo"]
    
    fig, ax = plt.subplots(figsize=(6, 4.5))
    labels = list(classes.keys())
    valores = list(classes.values())
    cores = PALETA[:len(labels)]
    
    wedges, texts, autotexts = ax.pie(
        valores, labels=None, autopct='%1.1f%%',
        colors=cores, startangle=90,
        textprops={'color': COR["text"], 'fontsize': 10, 'fontweight': 'bold'},
        pctdistance=0.6
    )
    legend_labels = [f"{l} — R$ {v:,.0f}" for l, v in zip(labels, valores)]
    ax.legend(wedges, legend_labels, loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=2,
              facecolor=COR["card"], edgecolor=COR["border"], fontsize=8)
    ax.set_title("Composicao da Carteira por Classe", color=COR["text"], fontsize=13, pad=15, fontweight='bold')
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=COR["bg"], edgecolor='none')
    plt.close(fig)


def grafico_rentabilidade(posicoes, path):
    """Barras horizontais: rentabilidade por ativo"""
    data = sorted(posicoes, key=lambda x: x["rent"])
    tickers = [p["ticker"] for p in data]
    rents = [p["rent"] for p in data]
    cores_bar = [COR["green"] if r >= 0 else COR["red"] for r in rents]
    
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(tickers, rents, color=cores_bar, height=0.6, edgecolor='white', linewidth=0.5)
    ax.axvline(x=0, color=COR["border"], linewidth=1.5)
    ax.set_xlabel("Rentabilidade (%)", color=COR["muted"], fontsize=9)
    ax.set_title("Rentabilidade por Ativo", color=COR["text"], fontsize=13, pad=12, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    for bar, val in zip(bars, rents):
        x_pos = bar.get_width()
        offset = 0.5 if val >= 0 else -0.5
        ha = 'left' if val >= 0 else 'right'
        ax.text(x_pos + offset, bar.get_y() + bar.get_height()/2, f'{val:+.1f}%',
                va='center', ha=ha, color=COR["text"], fontsize=8, fontweight='bold')
    
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=COR["bg"], edgecolor='none')
    plt.close(fig)


def grafico_aportes(aportes, path):
    """Barras: aportes mensais"""
    meses = [a[0] for a in aportes]
    valores = [a[1] for a in aportes]
    
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(meses, valores, color=COR["accent"], width=0.6, edgecolor='white', linewidth=0.5)
    ax.set_ylabel("Aporte (R$)", color=COR["muted"], fontsize=9)
    ax.set_title("Evolucao dos Aportes Mensais", color=COR["text"], fontsize=13, pad=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    ax.tick_params(axis='x', rotation=45)
    
    for bar, val in zip(bars, valores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 15,
                f'R$ {val:,.0f}', ha='center', va='bottom', color=COR["text"], fontsize=7, fontweight='bold')
    
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=COR["bg"], edgecolor='none')
    plt.close(fig)


def grafico_top5(posicoes, path):
    """Top 5 posicoes"""
    top = posicoes[:5]
    tickers = [p["ticker"] for p in top]
    custo_vals = [p["custo"] for p in top]
    merc_vals = [p["preco"] * p["qtd"] if p["preco"] else 0 for p in top]
    
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(tickers))
    h = 0.35
    ax.barh(y + h/2, custo_vals, h, label='Custo de Aquisicao', color=COR["accent"], edgecolor='white', linewidth=0.5)
    ax.barh(y - h/2, merc_vals, h, label='Valor de Mercado', color=COR["green"], edgecolor='white', linewidth=0.5)
    ax.set_yticks(y)
    ax.set_yticklabels(tickers, fontweight='bold')
    ax.set_xlabel("R$", color=COR["muted"], fontsize=9)
    ax.set_title("Top 5 Posicoes — Custo vs Valor de Mercado", color=COR["text"], fontsize=13, pad=12, fontweight='bold')
    ax.legend(loc="lower right", facecolor=COR["card"], edgecolor=COR["border"], fontsize=8)
    ax.grid(axis='x', alpha=0.3)
    
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor=COR["bg"], edgecolor='none')
    plt.close(fig)


def grafico_evolucao(aportes, path):
    """Evolucao do patrimonio: barras mensais + linha acumulada."""
    if not aportes:
        fig, ax = plt.subplots(figsize=(10, 1))
        fig.savefig(path, dpi=150, facecolor=COR["bg"], edgecolor="none")
        plt.close(fig)
        return
    
    meses = [a[0] for a in aportes]
    valores = [float(a[1]) for a in aportes]
    acum = []
    total = 0
    for v in valores:
        total += v
        acum.append(total)
    
    fig, ax1 = plt.subplots(figsize=(10, 4.2))
    fig.set_facecolor(COR["bg"])
    ax1.set_facecolor(COR["card"])
    
    x = np.arange(len(meses))
    
    bars = ax1.bar(x, valores, 0.6, color=COR["accent"], alpha=0.7, edgecolor="white",
                   linewidth=0.5, label="Aporte Mensal")
    ax1.set_ylabel("R$ (aporte)", fontsize=9, color=COR["muted"])
    ax1.set_xticks(x)
    ax1.set_xticklabels([m[5:7] + "/" + m[2:4] for m in meses], fontsize=8)
    ax1.grid(axis="y", alpha=0.3, color=COR["border"])
    
    ax2 = ax1.twinx()
    line = ax2.plot(x, acum, color=COR["green"], linewidth=2.5, marker="o", markersize=5,
                    markerfacecolor="white", markeredgecolor=COR["green"],
                    markeredgewidth=1.5, label="Acumulado")
    ax2.fill_between(x, 0, acum, color=COR["green"], alpha=0.08)
    ax2.set_ylabel("R$ (acumulado)", fontsize=9, color=COR["green"])
    
    if acum:
        ax2.annotate(f"R$ {acum[-1]:,.0f}", (x[-1], acum[-1]),
                    textcoords="offset points", xytext=(10, 5), fontsize=9,
                    fontweight="bold", color=COR["green"], ha="left")
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper left",
              frameon=True, facecolor=COR["white"], edgecolor=COR["border"])
    
    ax1.set_title("Evolucao do Patrimonio Investido", fontsize=12, fontweight="bold",
                  color=COR["text"], pad=15)
    
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=COR["bg"], edgecolor="none")
    plt.close(fig)


# ── Analises por ativo ──────────────────────────────────────────
def analisar_ativo(ticker, pos, hist):
    """Gera analise textual por ativo baseada nos dados"""
    analises = []
    
    # Tendencia curto prazo
    if ticker in hist and len(hist[ticker]) >= 3:
        recentes = hist[ticker][-3:]
        precos = [h["preco"] for h in recentes]
        if precos[0] > 0:
            var_3d = ((precos[-1] / precos[0]) - 1) * 100
            if var_3d > 2:
                analises.append(f"Tendencia de alta nos ultimos dias ({var_3d:+.1f}%)")
            elif var_3d < -2:
                analises.append(f"Tendencia de queda nos ultimos dias ({var_3d:+.1f}%)")
            else:
                analises.append(f"Lateralizado no curto prazo ({var_3d:+.1f}% em 3 dias)")
    
    # Rentabilidade
    if pos["rent"] > 5:
        analises.append(f"Forte valorizacao desde a compra ({pos['rent']:+.1f}%) — otimo momento")
    elif pos["rent"] > 0:
        analises.append(f"Leve valorizacao ({pos['rent']:+.1f}%) — mantendo")
    elif pos["rent"] > -5:
        analises.append(f"Leve desvalorizacao ({pos['rent']:+.1f}%) — dentro do esperado")
    else:
        analises.append(f"Queda significativa ({pos['rent']:+.1f}%) — requer atencao")
    
    # Concentracao
    pct = (pos["custo"] / pos.get("_custo_total", 1)) * 100
    if pct > 20:
        analises.append(f"ATENCAO: Concentracao elevada ({pct:.1f}% da carteira)")
    
    return " | ".join(analises) if analises else "Sem dados suficientes para analise."


# ── PDF ─────────────────────────────────────────────────────────
def build_pdf(data, graficos, output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
    )
    
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle('Title2', parent=styles['Title'],
        fontSize=24, textColor=COR["accent"], spaceAfter=2*mm,
        alignment=TA_LEFT, fontName='Helvetica-Bold', leading=28)
    style_h1 = ParagraphStyle('H1', parent=styles['Heading1'],
        fontSize=16, textColor=COR["text"], spaceBefore=10*mm, spaceAfter=4*mm,
        fontName='Helvetica-Bold')
    style_h2 = ParagraphStyle('H2', parent=styles['Heading2'],
        fontSize=12, textColor=COR["accent"], spaceBefore=6*mm, spaceAfter=3*mm,
        fontName='Helvetica-Bold')
    style_body = ParagraphStyle('Body2', parent=styles['Normal'],
        fontSize=9, textColor=COR["text"], leading=14,
        fontName='Helvetica')
    style_metric_val = ParagraphStyle('MetricVal', parent=styles['Normal'],
        fontSize=16, textColor=COR["accent"], fontName='Helvetica-Bold',
        alignment=TA_CENTER, leading=18)
    style_metric_label = ParagraphStyle('MetricLab', parent=styles['Normal'],
        fontSize=8, textColor=COR["muted"], fontName='Helvetica',
        alignment=TA_CENTER)
    style_small = ParagraphStyle('Small', parent=styles['Normal'],
        fontSize=7, textColor=COR["muted"], fontName='Helvetica')
    style_analise = ParagraphStyle('Analise', parent=styles['Normal'],
        fontSize=8, textColor=COR["muted"], leading=11, fontName='Helvetica-Oblique')
    
    story = []
    
    # ── CAPA ──
    story.append(Spacer(1, 25*mm))
    story.append(Paragraph("RELATORIO EXECUTIVO", style_title))
    story.append(Paragraph("Carteira de Investimentos — Prof. Marcos", 
        ParagraphStyle('sub', parent=styles['Normal'], fontSize=13, textColor=COR["muted"],
        fontName='Helvetica', spaceAfter=2*mm)))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COR["accent"], spaceAfter=6*mm))
    
    # Metricas
    custo = data["custo_total"]
    mercado = data["mercado_total"]
    rent = data["rent_total"]
    lucro = mercado - custo
    
    m_data = [
        [Paragraph("PATRIMONIO TOTAL", style_metric_label),
         Paragraph("RENTABILIDADE", style_metric_label),
         Paragraph("LUCRO/PREJUIZO", style_metric_label),
         Paragraph("ATIVOS", style_metric_label)],
        [Paragraph(f"R$ {mercado:,.2f}", style_metric_val),
         Paragraph(f"{rent:+.1f}%", ParagraphStyle('v', parent=style_metric_val,
             textColor=COR["green"] if rent >= 0 else COR["red"])),
         Paragraph(f"R$ {lucro:+,.2f}", ParagraphStyle('v2', parent=style_metric_val,
             textColor=COR["green"] if lucro >= 0 else COR["red"], fontSize=14)),
         Paragraph(f"{len(data['posicoes'])}", style_metric_val)],
    ]
    t_metricas = Table(m_data, colWidths=[48*mm, 42*mm, 42*mm, 40*mm])
    t_metricas.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, 1), COR["white"]),
        ('BOX', (0, 0), (-1, -1), 1, COR["border"]),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, COR["border"]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_metricas)
    
    story.append(Spacer(1, 6*mm))
    story.append(Image(graficos["evolucao"], width=170*mm, height=72*mm))
    
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(f"Professor Marcos | {data['data']}", style_small))
    story.append(Paragraph("Fluxo de Investimentos • Gerado por Hermes AI Agent", style_small))
    
    story.append(PageBreak())
    
    # ── 1. COMPOSICAO ──
    story.append(Paragraph("1. Visao Geral da Carteira", style_h1))
    story.append(Paragraph(
        f"A carteira e composta por <b>{len(data['posicoes'])} ativos</b>, "
        f"com custo total de <b>R$ {custo:,.2f}</b> e valor de mercado estimado em "
        f"<b>R$ {mercado:,.2f}</b>. A rentabilidade atual e de "
        f"<b><font color='{COR['green'] if rent >= 0 else COR['red']}'>{rent:+.1f}%</font></b>. "
        f"O perfil e predominantemente <b>buy and hold</b>, com compras regulares desde abril/2026.",
        style_body))
    
    story.append(Spacer(1, 4*mm))
    story.append(Image(graficos["composicao"], width=150*mm, height=110*mm))
    
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("Posicoes Detalhadas", style_h2))
    
    # Tabela de posicoes com analise
    t_header = ["Ativo", "Nome", "Qtd", "PM", "Preco Atual", "Rent%", "Peso"]
    t_data = [t_header]
    for p in data["posicoes"]:
        merc = p["preco"] * p["qtd"] if p["preco"] else 0
        peso = (p["custo"] / custo * 100) if custo else 0
        color_rent = COR["green"] if p["rent"] >= 0 else COR["red"]
        t_data.append([
            Paragraph(f"<b>{p['ticker']}</b>", ParagraphStyle('ticker', parent=style_body, fontSize=8)),
            Paragraph(p["nome"][:22], ParagraphStyle('nome', parent=style_body, fontSize=7)),
            Paragraph(f"{p['qtd']:.0f}", style_body),
            Paragraph(f"R$ {p['pm']:.2f}", style_body),
            Paragraph(f"R$ {p['preco']:.2f}" if p["preco"] else "—", style_body),
            Paragraph(f'<font color="{color_rent}"><b>{p["rent"]:+.1f}%</b></font>', style_body),
            Paragraph(f"{peso:.1f}%", style_body),
        ])
    
    col_w = [16*mm, 48*mm, 14*mm, 22*mm, 24*mm, 18*mm, 15*mm]
    t = Table(t_data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR["accent"]),
        ('TEXTCOLOR', (0, 0), (-1, 0), COR["white"]),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, COR["border"]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
    ]))
    story.append(t)
    
    story.append(PageBreak())
    
    # ── 1B. ANALISE DE ALOCACAO ESTRATEGICA (com IR e Rebalanceamento) ──
    story.append(Paragraph("1B. Analise de Alocacao Estrategica", style_h1))
    story.append(Paragraph(
        "A tabela abaixo compara a distribuicao atual da carteira com a alocacao alvo, "
        "agora com valores em R$, estimativa de IR em caso de venda do excesso, e "
        "prioridade para os proximos aportes (rebalanceamento por fluxo, sem vender).",
        style_body))
    story.append(Spacer(1, 4*mm))
    
    # Tabela alocacao avancada
    t_aloc_h = ["Classe", "% Atual", "% Alvo", "Gap R$", "Acao", "IR Est.", "Prior."]
    t_aloc_d = [t_aloc_h]
    for r in data["aloc_avancada"]:
        color_gap = COR["green"] if r["gap"] < 0 else COR["red"]
        ir_str = f"R$ {r['ir_estimado_venda']:,.2f}" if r['ir_estimado_venda'] and r['ir_estimado_venda'] > 0 else "—"
        t_aloc_d.append([
            Paragraph(f"<b>{r['classe']}</b>", style_body),
            Paragraph(f"{r['pct_atual']:.1f}%", style_body),
            Paragraph(f"{r['pct_alvo']:.0f}%", style_body),
            Paragraph(f'<font color="{color_gap}"><b>R$ {r["gap_rs"]:+,.0f}</b></font>', style_body),
            Paragraph(f"{r['acao_rebalanceamento']}", style_body),
            Paragraph(ir_str, style_body),
            Paragraph(f"<b>#{r['prioridade_aporte']}</b>", style_body),
        ])
    
    col_aloc = [28*mm, 22*mm, 22*mm, 22*mm, 34*mm, 20*mm, 14*mm]
    t_aloc = Table(t_aloc_d, colWidths=col_aloc, repeatRows=1)
    t_aloc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR["accent"]),
        ('TEXTCOLOR', (0, 0), (-1, 0), COR["white"]),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, COR["border"]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
    ]))
    story.append(t_aloc)
    
    story.append(Spacer(1, 5*mm))
    
    # Paragrafo de rebalanceamento por fluxo
    reb_text = modulo_alocacao_ir.paragrafo_rebalanceamento_fluxo(data["aloc_avancada"])
    story.append(Paragraph(reb_text, style_body))
    
    story.append(Spacer(1, 6*mm))
    story.append(Image(graficos["alocacao"], width=160*mm, height=90*mm))
    
    story.append(PageBreak())
    
    # ── 2. ANALISE POR ATIVO ──
    story.append(Paragraph("2. Analise Individual por Ativo", style_h1))
    story.append(Paragraph(
        "Abaixo, uma analise sucinta de cada ativo em carteira, considerando tendencia "
        "recente de precos, rentabilidade desde a compra e concentracao na carteira.",
        style_body))
    
    custo_total_local = sum(p["custo"] for p in data["posicoes"])
    for p in data["posicoes"]:
        p["_custo_total"] = custo_total_local
    
    for i, p in enumerate(data["posicoes"]):
        merc = p["preco"] * p["qtd"] if p["preco"] else 0
        peso = (p["custo"] / custo_total_local * 100) if custo_total_local else 0
        color_rent = COR["green"] if p["rent"] >= 0 else COR["red"]
        analise = analisar_ativo(p["ticker"], p, data["hist_cot"])
        
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            f"<b>{p['ticker']}</b> — {p['nome']}",
            ParagraphStyle('ativo_title', parent=style_body, fontSize=10, fontName='Helvetica-Bold',
                          textColor=COR["accent"])))
        
        info = (f"<b>{p['qtd']:.0f} unidades</b> | PM R$ {p['pm']:.2f} | "
                f"Preco atual: R$ {p['preco']:.2f} | "
                f"<font color='{color_rent}'><b>{p['rent']:+.1f}%</b></font> | "
                f"Peso: {peso:.1f}% | Custo: R$ {p['custo']:,.2f}")
        story.append(Paragraph(info, style_body))
        story.append(Paragraph(f"<i>📊 {analise}</i>", style_analise))
    
    story.append(PageBreak())
    
    # ── 3. GRAFICOS ──
    story.append(Paragraph("3. Graficos e Tendencias", style_h1))
    
    story.append(Paragraph("Rentabilidade por Ativo", style_h2))
    story.append(Image(graficos["rentabilidade"], width=160*mm, height=100*mm))
    
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("Top 5 Posicoes — Custo vs Mercado", style_h2))
    story.append(Image(graficos["top5"], width=160*mm, height=80*mm))
    
    story.append(PageBreak())
    
    # ── 4. APORTES ──
    story.append(Paragraph("4. Historico de Aportes", style_h1))
    story.append(Image(graficos["aportes"], width=160*mm, height=80*mm))
    
    story.append(Spacer(1, 4*mm))
    t_ap = [["Mes", "Aporte (R$)", "Acumulado (R$)", "Variacao"]]
    acum = 0
    prev = 0
    for mes, val in data["aportes"]:
        acum += val
        var = ((val / prev) - 1) * 100 if prev > 0 else 0
        var_str = f"{var:+.0f}%" if prev > 0 else "—"
        t_ap.append([f"{mes[5:7]}/{mes[0:4]}", f"R$ {val:,.2f}", f"R$ {acum:,.2f}", var_str])
        prev = val
    
    col_ap = [38*mm, 38*mm, 38*mm, 30*mm]
    t2 = Table(t_ap, colWidths=col_ap, repeatRows=1)
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR["accent"]),
        ('TEXTCOLOR', (0, 0), (-1, 0), COR["white"]),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, COR["border"]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
    ]))
    story.append(t2)
    
    # ── 5. ULTIMAS OPERACOES ──
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("5. Ultimas 12 Operacoes", style_h1))
    t_op = [["Data", "Ativo", "Operacao", "Qtd", "Preco Un.", "Total"]]
    for op in data["ultimas_ops"]:
        emoji = "🟢 Compra" if op[2] == "COMPRA" else "🔴 Venda"
        total = op[3] * op[4]
        t_op.append([
            op[0].strftime("%d/%m/%Y") if hasattr(op[0], 'strftime') else str(op[0]), op[1], emoji,
            f"{op[3]:.0f}", f"R$ {op[4]:.2f}", f"R$ {total:.2f}"
        ])
    
    t3 = Table(t_op, colWidths=[28*mm, 22*mm, 28*mm, 16*mm, 28*mm, 26*mm], repeatRows=1)
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR["accent"]),
        ('TEXTCOLOR', (0, 0), (-1, 0), COR["white"]),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, COR["border"]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
    ]))
    story.append(t3)
    
    story.append(PageBreak())
    
    # ── 5B. SITUACAO TRIBUTARIA ──
    story.append(Spacer(1, 6*mm))
    
    trib_flowables = modulo_tributario.tributario_para_pdf(data["trib"])
    for flowable in trib_flowables:
        story.append(flowable)
    
    story.append(PageBreak())
    
    # ── 6. ALERTAS INTELIGENTES ──
    alertas_flowables = modulo_alertas_inteligentes.alertas_para_pdf(data["alertas_int"])
    if alertas_flowables:
        story.append(Paragraph("6. Alertas Inteligentes", style_h1))
        for flowable in alertas_flowables:
            story.append(flowable)
    
    # ── 7. INDICADORES ──
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("7. Indicadores de Mercado", style_h1))
    if data["ifix"]:
        cor_ifix = COR["green"] if float(data['ifix'][1]) >= 0 else COR["red"]
        story.append(Paragraph(
            f"<b>IFIX:</b> R$ {float(data['ifix'][0]):,.2f} "
            f"(<font color='{cor_ifix}'><b>{float(data['ifix'][1]):+.2f}%</b></font>) — "
            f"Indice de Fundos Imobiliarios",
            style_body))
    
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f"<b>CDI (estimado):</b> ~14.15% a.a. — rentabilidade acumulada no periodo "
        f"aproximadamente 3.5% desde abril/2026.",
        style_body))
    
    # ── 8. ANALISE SETORIAL ──
    story.append(PageBreak())
    story.append(Spacer(1, 4*mm))
    
    setorial_flowables = modulo_setorial.setorial_para_pdf(
        data["setorial"],
        {"acoes_setor": graficos["setorial_acoes"], "fiis_segmento": graficos["setorial_fiis"],
         "fiis_tijolo_papel": graficos["setorial_tijolo_papel"]}
    )
    for flowable in setorial_flowables:
        story.append(flowable)
    
    # ── 9. RENDA PASSIVA ──
    story.append(PageBreak())
    story.append(Spacer(1, 4*mm))
    
    renda_flowables = modulo_renda_passiva.renda_passiva_para_pdf(
        data["renda_passiva"],
        {"evolucao_proventos": graficos["evolucao_proventos"], "yield_on_cost": graficos["yield_on_cost"]}
    )
    for flowable in renda_flowables:
        story.append(flowable)
    
    # ── 9B. ANÁLISE FUNDAMENTALISTA ──
    story.append(PageBreak())
    
    fund_flowables = modulo_fundamentalista.fundamentalista_para_pdf(
        data["fundamentalista"],
        {"f_roe": graficos["f_roe"], "f_pvp": graficos["f_pvp"],
         "f_dy": graficos["f_dy"], "f_ev_ebitda": graficos["f_ev_ebitda"]}
    )
    for flowable in fund_flowables:
        story.append(flowable)
    
    # ── 10. BENCHMARKING ──
    story.append(PageBreak())
    
    bench_flowables = modulo_benchmarking.benchmarking_para_pdf(
        data["benchmarking"], graficos["benchmarking"]
    )
    for flowable in bench_flowables:
        story.append(flowable)
    
    # ── 11. RISCO E VOLATILIDADE ──
    story.append(PageBreak())
    
    risco_flowables = modulo_risco.risco_para_pdf(
        data["risco"],
        {"heatmap_correlacao": graficos["heatmap_correlacao"], "drawdown": graficos["drawdown"]}
    )
    for flowable in risco_flowables:
        story.append(flowable)
    
    # ── DISCLAIMER ──
    story.append(Spacer(1, 15*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COR["border"]))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "Este relatorio e gerado automaticamente pelo Hermes AI Agent. "
        "As analises tem carater informativo e nao constituem recomendacao de investimento. "
        "Cotacoes podem ter defasagem de ate 24h. Dados obtidos via Yahoo Finance e brapi.dev.",
        style_small))
    
    doc.build(story)
    return output_path


# ── Upload Google Drive ─────────────────────────────────────────
def upload_to_drive(filepath, filename, token_path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    
    with open(token_path) as f:
        t = json.load(f)
    
    creds = Credentials(
        token=t['token'], refresh_token=t['refresh_token'],
        token_uri=t.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=t['client_id'], client_secret=t['client_secret'],
        scopes=t.get('scopes', [])
    )
    if creds.expired:
        creds.refresh(Request())
        with open(token_path, 'w') as f:
            f.write(creds.to_json())
    
    service = build('drive', 'v3', credentials=creds)
    
    folder_name = "Relatorios Executivos"
    q = f"name='{folder_name}' and '{DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resp = service.files().list(q=q, fields='files(id)').execute()
    files = resp.get('files', [])
    if files:
        folder_id = files[0]['id']
    else:
        folder_meta = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [DRIVE_FOLDER_ID]}
        folder = service.files().create(body=folder_meta, fields='id').execute()
        folder_id = folder['id']
    
    media = MediaFileUpload(filepath, mimetype='application/pdf', resumable=True)
    file_meta = {'name': filename, 'parents': [folder_id]}
    uploaded = service.files().create(body=file_meta, media_body=media, fields='id,webViewLink').execute()
    service.permissions().create(fileId=uploaded['id'], body={'type': 'anyone', 'role': 'reader'}).execute()
    return uploaded.get('webViewLink')


# ── MAIN ────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("RELATORIO EXECUTIVO — Carteira Prof. Marcos (Tema CLEAN)")
    print("=" * 60)
    
    print("\n[1/4] Coletando dados...")
    data = get_data()
    print(f"  {len(data['posicoes'])} posicoes | Custo R$ {data['custo_total']:,.2f} | Mercado R$ {data['mercado_total']:,.2f}")
    
    print("\n[2/4] Gerando graficos...")
    graficos = {}
    for nome, func, fname in [
        ("Composicao", grafico_composicao, "composicao.png"),
        ("Rentabilidade", grafico_rentabilidade, "rentabilidade.png"),
        ("Aportes", grafico_aportes, "aportes.png"),
        ("Top 5", grafico_top5, "top5.png"),
        ("Alocacao", grafico_alocacao, "alocacao.png"),
        ("Evolucao", grafico_evolucao, "evolucao.png"),
    ]:
        path = os.path.join(TMPDIR, fname)
        if nome == "Alocacao":
            func(data["aloc"], path)
        elif nome == "Aportes":
            func(data["aportes"], path)
        elif nome == "Evolucao":
            func(data["aportes"], path)
        else:
            func(data["posicoes"], path)
        graficos[fname.replace(".png", "")] = path
        print(f"  ✓ {nome}")
    
    # Graficos setoriais
    path_set_acoes = os.path.join(TMPDIR, "setorial_acoes.png")
    modulo_setorial.grafico_setorial_acoes(data["setorial"]["acoes_por_setor"], path_set_acoes)
    graficos["setorial_acoes"] = path_set_acoes
    print("  ✓ Setorial - Acoes")
    
    path_set_fiis = os.path.join(TMPDIR, "setorial_fiis.png")
    modulo_setorial.grafico_setorial_fiis(data["setorial"]["fiis_por_segmento"], path_set_fiis)
    graficos["setorial_fiis"] = path_set_fiis
    print("  ✓ Setorial - FIIs")
    
    path_tijolo_papel = os.path.join(TMPDIR, "setorial_tijolo_papel.png")
    modulo_setorial.grafico_fiis_tijolo_papel(data["setorial"]["fiis_tijolo_papel"], path_tijolo_papel)
    graficos["setorial_tijolo_papel"] = path_tijolo_papel
    print("  ✓ Setorial - Tijolo vs Papel")
    
    # Graficos renda passiva
    path_evol_prov = os.path.join(TMPDIR, "evolucao_proventos.png")
    modulo_renda_passiva.grafico_evolucao_proventos(data["renda_passiva"]["proventos_por_mes"], path_evol_prov)
    graficos["evolucao_proventos"] = path_evol_prov
    print("  ✓ Renda Passiva - Evolucao")
    
    path_yoc = os.path.join(TMPDIR, "yield_on_cost.png")
    modulo_renda_passiva.grafico_yield_on_cost(data["renda_passiva"]["proventos_por_ativo"], path_yoc)
    graficos["yield_on_cost"] = path_yoc
    print("  ✓ Renda Passiva - Yield on Cost")
    
    # Graficos benchmarking
    path_bench = os.path.join(TMPDIR, "benchmarking.png")
    modulo_benchmarking.grafico_benchmarking(data["benchmarking"]["serie_twr"], path_bench)
    graficos["benchmarking"] = path_bench
    print("  ✓ Benchmarking")
    
    # Graficos risco
    path_heatmap = os.path.join(TMPDIR, "heatmap_correlacao.png")
    modulo_risco.grafico_heatmap_correlacao(data["risco"]["correlacao"], path_heatmap)
    graficos["heatmap_correlacao"] = path_heatmap
    print("  ✓ Risco - Heatmap")
    
    path_drawdown = os.path.join(TMPDIR, "drawdown.png")
    modulo_risco.grafico_drawdown(data["risco"]["drawdown"], path_drawdown)
    graficos["drawdown"] = path_drawdown
    print("  ✓ Risco - Drawdown")
    
    # ── Fundamentalista ──
    path_f_roe = os.path.join(TMPDIR, "fund_roe.png")
    modulo_fundamentalista.grafico_roe(data["fundamentalista"]["acoes"], path_f_roe)
    graficos["f_roe"] = path_f_roe
    print("  ✓ Fundamentalista - ROE")
    
    path_f_pvp = os.path.join(TMPDIR, "fund_pvp.png")
    modulo_fundamentalista.grafico_p_vp(data["fundamentalista"]["acoes"], path_f_pvp)
    graficos["f_pvp"] = path_f_pvp
    print("  ✓ Fundamentalista - P/VP")
    
    path_f_ev = os.path.join(TMPDIR, "fund_ev_ebitda.png")
    modulo_fundamentalista.grafico_ev_ebitda(data["fundamentalista"]["acoes"], path_f_ev)
    graficos["f_ev_ebitda"] = path_f_ev
    print("  ✓ Fundamentalista - EV/EBITDA")
    
    path_f_dy = os.path.join(TMPDIR, "fund_dy.png")
    modulo_fundamentalista.grafico_dividend_yield(
        data["fundamentalista"]["acoes"], data["fundamentalista"]["fiis"], path_f_dy)
    graficos["f_dy"] = path_f_dy
    print("  ✓ Fundamentalista - Dividend Yield")
    
    print("\n[3/4] Gerando PDF...")
    hoje = datetime.date.today().strftime("%Y-%m-%d")
    pdf_filename = f"Relatorio_Executivo_{hoje}.pdf"
    pdf_path = os.path.join(OUT_DIR, pdf_filename)
    build_pdf(data, graficos, pdf_path)
    size_kb = os.path.getsize(pdf_path) / 1024
    print(f"  ✓ PDF: {pdf_path} ({size_kb:.0f} KB)")
    
    print("\n[4/4] Upload Google Drive...")
    base = os.environ.get('HERMES_HOME', os.path.expanduser('~/.hermes'))
    token_path = base + '/google_token.json'
    link = upload_to_drive(pdf_path, pdf_filename, token_path)
    print(f"  ✓ Link: {link}")
    
    import shutil
    shutil.rmtree(TMPDIR, ignore_errors=True)
    
    print(f"\nLINK_FINAL={link}")
    return link


if __name__ == "__main__":
    main()
