#!/usr/bin/env python3
"""
Modulo Setorial — Analise Setorial e Geografica
=================================================
Adiciona analise setorial ao Relatorio Executivo:
  - Mapeamento de setores das acoes no banco de dados
  - Graficos de pizza: Acoes por Setor, FIIs por Segmento
  - Breakdown dos FIIs de papel por indexador (CDI vs IPCA+)
  - Formatadores para PDF (reportlab flowables)

Integracao: importado por relatorio_executivo.py ou usado standalone.
Autor: Hermes AI Agent
Data: 2026-07-19
"""

import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import psycopg2
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

# ── Mapeamento de indexadores para FIIs de papel ─────────────────
# KNCR11: Kinea Recebiveis — atrelado ao CDI
# CPTS11: Capitania Securities — papel atrelado ao IPCA+
FII_PAPEL_INDEXADOR = {
    "KNCR11": "CDI",
    "CPTS11": "IPCA+",
}

# ── Mapeamento Tijolo vs Papel para FIIs ─────────────────────────
# Tijolo: fundos que investem em imoveis fisicos (galpoes, lajes, shoppings, renda urbana)
# Papel: fundos que investem em titulos de divida imobiliaria (CRIs)
FII_TIJOLO_PAPEL = {
    "ALZR11": "Tijolo",
    "GARE11": "Tijolo",
    "HGLG11": "Tijolo",
    "HGRU11": "Tijolo",
    "KNRI11": "Tijolo",
    "MXRF11": "Tijolo",
    "CPTS11": "Papel",
    "KNCR11": "Papel",
    "MCHF11": "Papel",
    "VGHF11": "Papel",
}

# ── Mapeamento de setores para acoes ─────────────────────────────
# Usado por mapear_setores_acoes() para popular o campo 'setor'
MAPA_SETORES_ACOES = {
    "BBAS3": "Financeiro/Bancos",
    "BBDC4": "Financeiro/Bancos",
    "BBSE3": "Seguridade",
    "BEES3": "Financeiro/Bancos",
    "BRSR6": "Financeiro/Bancos",
    "CMIG4": "Energia Eletrica",
    "ITSA3": "Financeiro/Bancos",
    "JHSF3": "Construcao/Incorporacao",
    "KLBN3": "Papel/Celulose",
    "PETR4": "Petroleo/Gas",
    "POMO4": "Industrial/Siderurgia",
    "SANB3": "Financeiro/Bancos",
    "SAPR3": "Saneamento/Agro",
    "VALE3": "Mineracao",
    "VULC3": "Industrial",
    "WEGE3": "Industrial/Bens de Capital",
}


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 1: MAPEAMENTO DE SETORES                 ║
# ╚══════════════════════════════════════════════════════════════════╝

def mapear_setores_acoes() -> None:
    """
    Conecta ao banco e popula os setores das acoes (tipo='ACAO')
    que ainda estao com setor NULL ou vazio.

    Usa o mapeamento hardcoded em MAPA_SETORES_ACOES.

    Returns:
        None
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        for ticker, setor in MAPA_SETORES_ACOES.items():
            cur.execute("""
                UPDATE investimentos.ativos
                SET setor = %s
                WHERE ticker = %s
                  AND tipo = 'ACAO'
                  AND (setor IS NULL OR setor = '')
            """, (setor, ticker))

        conn.commit()
        print(f"[modulo_setorial] Setores atualizados para {len(MAPA_SETORES_ACOES)} acoes.")

    except Exception as e:
        conn.rollback()
        print(f"[modulo_setorial] Erro ao mapear setores: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 2: COMPUTACAO DOS DADOS                  ║
# ╚══════════════════════════════════════════════════════════════════╝

def compute_analise_setorial() -> dict:
    """
    Conecta ao banco e calcula a distribuicao setorial da carteira.

    Retorna um dicionario com tres blocos:
        - acoes_por_setor: distribuicao das acoes por setor
        - fiis_por_segmento: distribuicao dos FIIs por segmento
        - fiis_papel_indexador: breakdown dos FIIs de papel por indexador

    Returns:
        dict com a estrutura:
        {
            "acoes_por_setor": [
                {"setor": str, "valor": float, "pct": float, "tickers": [str, ...]},
                ...
            ],
            "fiis_por_segmento": [
                {"segmento": str, "valor": float, "pct": float, "tickers": [str, ...]},
                ...
            ],
            "fiis_papel_indexador": [
                {"indexador": str, "pct": float, "tickers": [str, ...]},
                ...
            ],
        }
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Query: junta posicoes, ativos e cotacao mais recente
    cur.execute("""
        SELECT
            p.ticker,
            p.quantidade_total,
            p.custo_total,
            c.fechamento AS preco_atual,
            a.nome,
            a.tipo,
            a.setor
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        LEFT JOIN LATERAL (
            SELECT fechamento
            FROM investimentos.cotacoes
            WHERE ticker = p.ticker
            ORDER BY data DESC
            LIMIT 1
        ) c ON true
        WHERE p.quantidade_total > 0
        ORDER BY a.tipo, p.custo_total DESC
    """)

    rows = cur.fetchall()
    conn.close()

    # ── Agrupa acoes por setor ───────────────────────────────────
    acoes_setor = {}  # setor -> {"valor": float, "tickers": list}
    total_acoes_valor = 0.0

    # ── Agrupa FIIs por segmento ─────────────────────────────────
    fiis_segmento = {}  # segmento -> {"valor": float, "tickers": list}
    total_fiis_valor = 0.0

    # ── FIIs de papel (para breakdown por indexador) ─────────────
    fiis_papel_indexador_map = {}  # indexador -> {"valor": float, "tickers": list}
    total_fiis_papel_valor = 0.0

    # ── FIIs Tijolo vs Papel ─────────────────────────────────────
    fiis_tijolo_papel_map = {}  # "Tijolo"|"Papel" -> {"valor": float, "tickers": list}
    total_fiis_tp_valor = 0.0

    for ticker, qtd, custo, preco_atual, nome, tipo, setor in rows:
        qtd = float(qtd)
        preco_atual = float(preco_atual) if preco_atual else 0.0
        valor_mercado = preco_atual * qtd

        setor = (setor or "").strip()

        if tipo == "ACAO":
            chave = setor if setor else "Nao Classificado"
            if chave not in acoes_setor:
                acoes_setor[chave] = {"valor": 0.0, "tickers": []}
            acoes_setor[chave]["valor"] += valor_mercado
            acoes_setor[chave]["tickers"].append(ticker)
            total_acoes_valor += valor_mercado

        elif tipo == "FII":
            segmento = setor if setor else "Nao Classificado"
            if segmento not in fiis_segmento:
                fiis_segmento[segmento] = {"valor": 0.0, "tickers": []}
            fiis_segmento[segmento]["valor"] += valor_mercado
            fiis_segmento[segmento]["tickers"].append(ticker)
            total_fiis_valor += valor_mercado

            # Verifica se eh FII de papel com indexador conhecido
            if segmento == "Papel/CRI" and ticker in FII_PAPEL_INDEXADOR:
                idx = FII_PAPEL_INDEXADOR[ticker]
                if idx not in fiis_papel_indexador_map:
                    fiis_papel_indexador_map[idx] = {"valor": 0.0, "tickers": []}
                fiis_papel_indexador_map[idx]["valor"] += valor_mercado
                fiis_papel_indexador_map[idx]["tickers"].append(ticker)
                total_fiis_papel_valor += valor_mercado

            # Classifica Tijolo vs Papel
            tipo_fii = FII_TIJOLO_PAPEL.get(ticker, "Nao Classificado")
            if tipo_fii not in fiis_tijolo_papel_map:
                fiis_tijolo_papel_map[tipo_fii] = {"valor": 0.0, "tickers": []}
            fiis_tijolo_papel_map[tipo_fii]["valor"] += valor_mercado
            fiis_tijolo_papel_map[tipo_fii]["tickers"].append(ticker)
            total_fiis_tp_valor += valor_mercado

    # ── Formata saida: acoes por setor ───────────────────────────
    acoes_por_setor = []
    for setor, dados in sorted(acoes_setor.items(), key=lambda x: -x[1]["valor"]):
        pct = round((dados["valor"] / total_acoes_valor * 100), 1) if total_acoes_valor > 0 else 0.0
        acoes_por_setor.append({
            "setor": setor,
            "valor": round(dados["valor"], 2),
            "pct": pct,
            "tickers": sorted(dados["tickers"]),
        })

    # ── Formata saida: FIIs por segmento ─────────────────────────
    fiis_por_segmento = []
    for segmento, dados in sorted(fiis_segmento.items(), key=lambda x: -x[1]["valor"]):
        pct = round((dados["valor"] / total_fiis_valor * 100), 1) if total_fiis_valor > 0 else 0.0
        fiis_por_segmento.append({
            "segmento": segmento,
            "valor": round(dados["valor"], 2),
            "pct": pct,
            "tickers": sorted(dados["tickers"]),
        })

    # ── Formata saida: FIIs de papel por indexador ───────────────
    fiis_papel_indexador = []
    for indexador, dados in sorted(fiis_papel_indexador_map.items(), key=lambda x: -x[1]["valor"]):
        pct = round((dados["valor"] / total_fiis_papel_valor * 100), 1) if total_fiis_papel_valor > 0 else 0.0
        fiis_papel_indexador.append({
            "indexador": indexador,
            "pct": pct,
            "tickers": sorted(dados["tickers"]),
        })

    # ── Formata saida: FIIs Tijolo vs Papel ──────────────────────
    fiis_tijolo_papel = []
    for tipo, dados in sorted(fiis_tijolo_papel_map.items(), key=lambda x: -x[1]["valor"]):
        pct = round((dados["valor"] / total_fiis_tp_valor * 100), 1) if total_fiis_tp_valor > 0 else 0.0
        fiis_tijolo_papel.append({
            "tipo": tipo,
            "valor": round(dados["valor"], 2),
            "pct": pct,
            "tickers": sorted(dados["tickers"]),
        })

    return {
        "acoes_por_setor": acoes_por_setor,
        "fiis_por_segmento": fiis_por_segmento,
        "fiis_papel_indexador": fiis_papel_indexador,
        "fiis_tijolo_papel": fiis_tijolo_papel,
    }


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 3: GERACAO DE GRAFICOS                   ║
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


def grafico_setorial_acoes(acoes_por_setor: list, path: str) -> str:
    """
    Gera grafico de pizza com a distribuicao das acoes por setor.

    Args:
        acoes_por_setor: lista de dicts (formato de compute_analise_setorial)
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    if not acoes_por_setor:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.text(0.5, 0.5, "Sem dados de acoes", ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=COR["muted"])
        ax.set_title("Acoes por Setor", color=COR["text"], fontsize=13,
                     pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    labels = [f"{s['setor']}" for s in acoes_por_setor]
    valores = [s["pct"] for s in acoes_por_setor]
    cores = PALETA[:len(labels)]

    fig, ax = plt.subplots(figsize=(6, 4.5))

    wedges, texts, autotexts = ax.pie(
        valores, labels=None, autopct='%1.1f%%',
        colors=cores, startangle=90,
        textprops={'color': COR["text"], 'fontsize': 9, 'fontweight': 'bold'},
        pctdistance=0.6,
        wedgeprops={'edgecolor': 'white', 'linewidth': 0.8},
    )

    # Legenda com valor em R$
    legend_labels = [
        f"{s['setor']} — R$ {s['valor']:,.0f} ({s['pct']:.1f}%)"
        for s in acoes_por_setor
    ]
    ax.legend(
        wedges, legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=1 if len(legend_labels) <= 6 else 2,
        facecolor=COR["card"], edgecolor=COR["border"], fontsize=7.5,
    )

    ax.set_title("Acoes por Setor", color=COR["text"], fontsize=13,
                 pad=15, fontweight='bold')

    return _salvar_figura(fig, path)


def grafico_setorial_fiis(fiis_por_segmento: list, path: str) -> str:
    """
    Gera grafico de pizza com a distribuicao dos FIIs por segmento.

    Args:
        fiis_por_segmento: lista de dicts (formato de compute_analise_setorial)
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    if not fiis_por_segmento:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.text(0.5, 0.5, "Sem dados de FIIs", ha='center', va='center',
                transform=ax.transAxes, fontsize=12, color=COR["muted"])
        ax.set_title("FIIs por Segmento", color=COR["text"], fontsize=13,
                     pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    labels = [f"{s['segmento']}" for s in fiis_por_segmento]
    valores = [s["pct"] for s in fiis_por_segmento]
    cores = PALETA[:len(labels)]

    fig, ax = plt.subplots(figsize=(6, 4.5))

    wedges, texts, autotexts = ax.pie(
        valores, labels=None, autopct='%1.1f%%',
        colors=cores, startangle=90,
        textprops={'color': COR["text"], 'fontsize': 9, 'fontweight': 'bold'},
        pctdistance=0.6,
        wedgeprops={'edgecolor': 'white', 'linewidth': 0.8},
    )

    # Legenda com valor em R$
    legend_labels = [
        f"{s['segmento']} — R$ {s['valor']:,.0f} ({s['pct']:.1f}%)"
        for s in fiis_por_segmento
    ]
    ax.legend(
        wedges, legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=1,
        facecolor=COR["card"], edgecolor=COR["border"], fontsize=7.5,
    )

    ax.set_title("FIIs por Segmento", color=COR["text"], fontsize=13,
                 pad=15, fontweight='bold')

    return _salvar_figura(fig, path)


def grafico_fiis_indexador(fiis_papel_indexador: list, path: str) -> str:
    """
    Gera grafico de pizza ou barra com o breakdown dos FIIs de papel
    por indexador (CDI vs IPCA+).

    Args:
        fiis_papel_indexador: lista de dicts (formato de compute_analise_setorial)
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    if not fiis_papel_indexador:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        ax.text(0.5, 0.5, "Sem FIIs de papel classificados\npor indexador",
                ha='center', va='center', transform=ax.transAxes,
                fontsize=11, color=COR["muted"])
        ax.set_title("FIIs de Papel por Indexador", color=COR["text"],
                     fontsize=13, pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    labels = [f"{i['indexador']}" for i in fiis_papel_indexador]
    valores = [i["pct"] for i in fiis_papel_indexador]

    # Cores especificas: CDI = accent (azul), IPCA+ = purple
    cores_idx = {
        "CDI": COR["accent"],
        "IPCA+": COR["purple"],
    }
    cores = [cores_idx.get(lbl, PALETA[j % len(PALETA)])
             for j, lbl in enumerate(labels)]

    fig, ax = plt.subplots(figsize=(5, 3.5))

    wedges, texts, autotexts = ax.pie(
        valores, labels=None, autopct='%1.1f%%',
        colors=cores, startangle=90,
        textprops={'color': COR["text"], 'fontsize': 11, 'fontweight': 'bold'},
        pctdistance=0.55,
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.2},
        explode=[0.03] * len(valores),
    )

    # Legenda com tickers
    legend_labels = [
        f"{i['indexador']} ({i['pct']:.1f}%): {', '.join(i['tickers'])}"
        for i in fiis_papel_indexador
    ]
    ax.legend(
        wedges, legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=1,
        facecolor=COR["card"], edgecolor=COR["border"], fontsize=8,
    )

    ax.set_title("FIIs de Papel por Indexador", color=COR["text"],
                 fontsize=12, pad=15, fontweight='bold')

    return _salvar_figura(fig, path)


def grafico_fiis_tijolo_papel(fiis_tijolo_papel: list, path: str) -> str:
    """
    Gera grafico de pizza com a classificacao Tijolo vs Papel dos FIIs.

    Args:
        fiis_tijolo_papel: lista de dicts (formato de compute_analise_setorial)
        path: caminho onde salvar o PNG

    Returns:
        str: caminho do arquivo PNG salvo
    """
    if not fiis_tijolo_papel:
        fig, ax = plt.subplots(figsize=(5, 3.5))
        ax.text(0.5, 0.5, "Sem dados de FIIs", ha='center', va='center',
                transform=ax.transAxes, fontsize=11, color=COR["muted"])
        ax.set_title("FIIs: Tijolo vs Papel", color=COR["text"],
                     fontsize=13, pad=15, fontweight='bold')
        return _salvar_figura(fig, path)

    labels = [f"{tp['tipo']}" for tp in fiis_tijolo_papel]
    valores = [tp["pct"] for tp in fiis_tijolo_papel]

    # Cores: Tijolo = laranja/terracota, Papel = azul accent
    cores_tp = {
        "Tijolo": COR["orange"],
        "Papel": COR["accent"],
    }
    cores = [cores_tp.get(lbl, PALETA[j % len(PALETA)])
             for j, lbl in enumerate(labels)]

    fig, ax = plt.subplots(figsize=(5, 3.5))

    wedges, texts, autotexts = ax.pie(
        valores, labels=None, autopct='%1.1f%%',
        colors=cores, startangle=90,
        textprops={'color': COR["text"], 'fontsize': 11, 'fontweight': 'bold'},
        pctdistance=0.55,
        wedgeprops={'edgecolor': 'white', 'linewidth': 1.2},
        explode=[0.03] * len(valores),
    )

    # Legenda com tickers
    legend_labels = [
        f"{tp['tipo']}: R$ {tp['valor']:,.0f} ({tp['pct']:.1f}%) — {', '.join(tp['tickers'])}"
        for tp in fiis_tijolo_papel
    ]
    ax.legend(
        wedges, legend_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=1,
        facecolor=COR["card"], edgecolor=COR["border"], fontsize=7.5,
    )

    ax.set_title("FIIs: Tijolo vs Papel", color=COR["text"],
                 fontsize=12, pad=15, fontweight='bold')

    return _salvar_figura(fig, path)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  PARTE 4: FORMATADOR PARA PDF                   ║
# ╚══════════════════════════════════════════════════════════════════╝

def setorial_para_pdf(data: dict, graficos_paths: dict,
                      styles: dict = None) -> list:
    """
    Gera uma lista de flowables do ReportLab para a secao de
    Analise Setorial e Geografica.

    Args:
        data: dicionario retornado por compute_analise_setorial()
        graficos_paths: dict com os caminhos dos graficos:
            {
                "acoes_setor": str,   # path do PNG de acoes por setor
                "fiis_segmento": str, # path do PNG de FIIs por segmento
                "fiis_indexador": str, # path do PNG de FIIs por indexador
            }
        styles: dicionario opcional com estilos personalizados.
                Chaves aceitas: h1, h2, body, small, muted.

    Returns:
        Lista de flowables (Paragraph, Spacer, Image, Table)
    """
    # ── Estilos padrao ────────────────────────────────────────────
    default_styles = {
        "h1": ParagraphStyle(
            "SetorialH1",
            fontSize=16,
            textColor=COR["text"],
            spaceBefore=10,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "SetorialH2",
            fontSize=12,
            textColor=COR["accent"],
            spaceBefore=8,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "SetorialBody",
            fontSize=9,
            textColor=COR["text"],
            leading=14,
            fontName="Helvetica",
        ),
        "small": ParagraphStyle(
            "SetorialSmall",
            fontSize=8,
            textColor=COR["text"],
            leading=11,
            fontName="Helvetica",
        ),
        "muted": ParagraphStyle(
            "SetorialMuted",
            fontSize=8,
            textColor=COR["muted"],
            fontName="Helvetica-Oblique",
        ),
    }

    if styles:
        default_styles.update(styles)

    S = default_styles
    story = []

    # ── Cabecalho da secao ────────────────────────────────────────
    story.append(Paragraph("Analise Setorial e Geografica", S["h1"]))
    story.append(Paragraph(
        "Visao consolidada da distribuicao da carteira por setores "
        "(acoes) e segmentos (FIIs). O grafico de FIIs de Papel detalha "
        "a exposicao aos indexadores CDI e IPCA+, informacao relevante "
        "para a gestao de risco em cenarios de variacao da taxa de juros.",
        S["body"],
    ))
    story.append(Spacer(1, 6))

    # ── Secao: Acoes por Setor ────────────────────────────────────
    acoes = data.get("acoes_por_setor", [])
    if acoes:
        story.append(Paragraph("Acoes por Setor", S["h2"]))
        story.append(Paragraph(
            f"A carteira de acoes esta distribuida em "
            f"<b>{len(acoes)} setores</b>. Abaixo o detalhamento "
            f"por valor de mercado e percentual.",
            S["muted"],
        ))
        story.append(Spacer(1, 3))

        # Tabela resumo de acoes por setor
        t_header = [Paragraph("<b>Setor</b>", S["small"]),
                     Paragraph("<b>Valor (R$)</b>", S["small"]),
                     Paragraph("<b>%</b>", S["small"]),
                     Paragraph("<b>Tickers</b>", S["small"])]
        t_data = [t_header]
        for s in acoes:
            t_data.append([
                Paragraph(s["setor"], S["small"]),
                Paragraph(f"R$ {s['valor']:,.0f}", S["small"]),
                Paragraph(f"{s['pct']:.1f}%", S["small"]),
                Paragraph(", ".join(s["tickers"]), S["small"]),
            ])

        col_w = [38*mm, 30*mm, 16*mm, 76*mm]
        t = Table(t_data, colWidths=col_w, repeatRows=1)
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
        story.append(Spacer(1, 4))

    # ── Secao: FIIs por Segmento ──────────────────────────────────
    fiis = data.get("fiis_por_segmento", [])
    if fiis:
        story.append(Paragraph("FIIs por Segmento", S["h2"]))
        story.append(Paragraph(
            f"A carteira de FIIs esta distribuida em "
            f"<b>{len(fiis)} segmentos</b>.",
            S["muted"],
        ))
        story.append(Spacer(1, 3))

        # Tabela resumo de FIIs por segmento
        t_header = [Paragraph("<b>Segmento</b>", S["small"]),
                     Paragraph("<b>Valor (R$)</b>", S["small"]),
                     Paragraph("<b>%</b>", S["small"]),
                     Paragraph("<b>Tickers</b>", S["small"])]
        t_data = [t_header]
        for s in fiis:
            t_data.append([
                Paragraph(s["segmento"], S["small"]),
                Paragraph(f"R$ {s['valor']:,.0f}", S["small"]),
                Paragraph(f"{s['pct']:.1f}%", S["small"]),
                Paragraph(", ".join(s["tickers"]), S["small"]),
            ])

        t = Table(t_data, colWidths=col_w, repeatRows=1)
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
        story.append(Spacer(1, 4))

    # ── Secao: Graficos lado a lado ───────────────────────────────
    g_acoes = graficos_paths.get("acoes_setor", "")
    g_fiis = graficos_paths.get("fiis_segmento", "")

    if g_acoes or g_fiis:
        story.append(Spacer(1, 6))

        # Tabela com duas colunas para exibir os graficos lado a lado
        if g_acoes and g_fiis:
            # Ambos disponiveis: lado a lado
            img_acoes = Image(g_acoes, width=80*mm, height=60*mm)
            img_fiis = Image(g_fiis, width=80*mm, height=60*mm)
            t_graficos = Table([[img_acoes, img_fiis]], colWidths=[80*mm, 80*mm])
            t_graficos.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(t_graficos)
        elif g_acoes:
            story.append(Image(g_acoes, width=140*mm, height=100*mm))
        elif g_fiis:
            story.append(Image(g_fiis, width=140*mm, height=100*mm))

        story.append(Spacer(1, 4))

    # ── Secao: FIIs de Papel por Indexador ────────────────────────
    fiis_idx = data.get("fiis_papel_indexador", [])
    g_idx = graficos_paths.get("fiis_indexador", "")

    if fiis_idx or g_idx:
        story.append(Paragraph("FIIs de Papel: Exposicao por Indexador", S["h2"]))
        story.append(Paragraph(
            "Os FIIs de papel (CRIs) tem seus rendimentos atrelados a "
            "diferentes indexadores. Em cenarios de queda da Selic, "
            "papeis atrelados ao CDI tendem a perder rentabilidade, "
            "enquanto os atrelados ao IPCA+ oferecem protecao inflacionaria.",
            S["body"],
        ))
        story.append(Spacer(1, 3))

        if fiis_idx:
            # Tabela resumo de indexadores
            t_header = [Paragraph("<b>Indexador</b>", S["small"]),
                         Paragraph("<b>%</b>", S["small"]),
                         Paragraph("<b>Tickers</b>", S["small"])]
            t_data = [t_header]
            for i in fiis_idx:
                t_data.append([
                    Paragraph(f"<b>{i['indexador']}</b>", S["small"]),
                    Paragraph(f"{i['pct']:.1f}%", S["small"]),
                    Paragraph(", ".join(i["tickers"]), S["small"]),
                ])

            col_w_idx = [30*mm, 16*mm, 114*mm]
            t = Table(t_data, colWidths=col_w_idx, repeatRows=1)
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
            story.append(Spacer(1, 4))

        if g_idx:
            story.append(Image(g_idx, width=100*mm, height=70*mm))
            story.append(Spacer(1, 4))

    # ── Secao: FIIs Tijolo vs Papel ───────────────────────────────
    fiis_tp = data.get("fiis_tijolo_papel", [])
    g_tp = graficos_paths.get("fiis_tijolo_papel", "")

    if fiis_tp or g_tp:
        story.append(Paragraph("FIIs: Tijolo vs Papel", S["h2"]))
        story.append(Paragraph(
            "Classificacao binaria dos FIIs: <b>Tijolo</b> (imoveis fisicos — "
            "galpoes, lajes, shoppings, renda urbana) vs <b>Papel</b> "
            "(titulos de divida imobiliaria — CRIs atrelados a CDI ou IPCA+). "
            "FIIs de tijolo tendem a ser mais estaveis em cenarios de queda "
            "de juros (valorizacao dos imoveis), enquanto FIIs de papel sofrem "
            "impacto direto da Selic nos rendimentos.",
            S["body"],
        ))
        story.append(Spacer(1, 3))

        if fiis_tp:
            # Tabela resumo Tijolo vs Papel
            t_header = [Paragraph("<b>Tipo</b>", S["small"]),
                         Paragraph("<b>Valor (R$)</b>", S["small"]),
                         Paragraph("<b>%</b>", S["small"]),
                         Paragraph("<b>Tickers</b>", S["small"])]
            t_data = [t_header]
            for tp in fiis_tp:
                t_data.append([
                    Paragraph(f"<b>{tp['tipo']}</b>", S["small"]),
                    Paragraph(f"R$ {tp['valor']:,.0f}", S["small"]),
                    Paragraph(f"{tp['pct']:.1f}%", S["small"]),
                    Paragraph(", ".join(tp["tickers"]), S["small"]),
                ])

            t = Table(t_data, colWidths=col_w, repeatRows=1)
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
            story.append(Spacer(1, 4))

        if g_tp:
            story.append(Image(g_tp, width=120*mm, height=85*mm))
            story.append(Spacer(1, 4))

    return story


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    BLOCO DE TESTE / STANDALONE                  ║
# ╚══════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    """
    Executa o modulo de forma autonoma:
    1. Mapeia setores das acoes no banco
    2. Computa analise setorial
    3. Gera graficos em arquivos temporarios
    4. Exibe resumo no terminal
    """
    import tempfile

    print("=" * 60)
    print("  MODULO SETORIAL — Teste Standalone")
    print("=" * 60)

    # ── Passo 1: Mapear setores ──────────────────────────────────
    print("\n[1/4] Mapeando setores das acoes...")
    try:
        mapear_setores_acoes()
        print("  OK — Setores mapeados com sucesso.")
    except Exception as e:
        print(f"  ATENCAO: {e}")

    # ── Passo 2: Computar analise ─────────────────────────────────
    print("\n[2/4] Computando analise setorial...")
    data = compute_analise_setorial()

    print(f"\n  Acoes por Setor ({len(data['acoes_por_setor'])} setores):")
    for s in data["acoes_por_setor"]:
        print(f"    {s['setor']:35s}  R$ {s['valor']:>10,.0f}  ({s['pct']:>5.1f}%)  "
              f"[{', '.join(s['tickers'])}]")

    print(f"\n  FIIs por Segmento ({len(data['fiis_por_segmento'])} segmentos):")
    for s in data["fiis_por_segmento"]:
        print(f"    {s['segmento']:25s}  R$ {s['valor']:>10,.0f}  ({s['pct']:>5.1f}%)  "
              f"[{', '.join(s['tickers'])}]")

    print(f"\n  FIIs de Papel — Indexadores ({len(data['fiis_papel_indexador'])}):")
    for i in data["fiis_papel_indexador"]:
        print(f"    {i['indexador']:10s}  {i['pct']:>5.1f}%  [{', '.join(i['tickers'])}]")

    # ── Passo 3: Gerar graficos ───────────────────────────────────
    print("\n[3/4] Gerando graficos...")
    tmp = tempfile.mkdtemp(prefix="setorial_")

    g_acoes = grafico_setorial_acoes(
        data["acoes_por_setor"],
        os.path.join(tmp, "acoes_por_setor.png"),
    )
    print(f"  Acoes por Setor → {g_acoes}")

    g_fiis = grafico_setorial_fiis(
        data["fiis_por_segmento"],
        os.path.join(tmp, "fiis_por_segmento.png"),
    )
    print(f"  FIIs por Segmento → {g_fiis}")

    g_idx = grafico_fiis_indexador(
        data["fiis_papel_indexador"],
        os.path.join(tmp, "fiis_papel_indexador.png"),
    )
    print(f"  FIIs Indexador   → {g_idx}")

    # ── Passo 4: Testar PDF flowables ─────────────────────────────
    print("\n[4/4] Testando formatador PDF...")
    graficos_paths = {
        "acoes_setor": g_acoes,
        "fiis_segmento": g_fiis,
        "fiis_indexador": g_idx,
    }
    story = setorial_para_pdf(data, graficos_paths)
    print(f"  Flowables gerados: {len(story)} elementos")
    print(f"  Tipos: {', '.join(type(f).__name__ for f in story)}")

    print("\n" + "=" * 60)
    print("  TESTE CONCLUIDO COM SUCESSO")
    print(f"  Graficos em: {tmp}")
    print("=" * 60)
