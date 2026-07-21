#!/usr/bin/env python3
"""
Modulo Tributario — Situacao Tributaria da Carteira
====================================================
Calcula IR potencial, prejuizos compensaveis e gera formatadores
para PDF (reportlab) e Telegram.

Regimes:
  - ACOES (inclui ACAO, ETF, ETF_INTERNACIONAL, RENDA_FIXA):
      15% IR sobre ganho de capital. Isencao para vendas ate R$ 20.000/mes.
  - FIIs:
      20% IR sobre ganho de capital. Sem isencao.

Prejuizos podem compensar ganhos DENTRO do mesmo regime.
"""

import psycopg2
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import mm

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

# Tipos de ativo que seguem o regime de ACOES (15% IR, isencao < R$20k)
REGIME_ACOES = {"ACAO", "ETF", "ETF_INTERNACIONAL", "RENDA_FIXA"}

# Tipos que seguem regime FII (20% IR, sem isencao)
REGIME_FIIS = {"FII"}


# ---------------------------------------------------------------------------
# Funcoes auxiliares puras
# ---------------------------------------------------------------------------

def _classificar_regime(tipo: str) -> str:
    """Retorna 'acoes' ou 'fiis' conforme o tipo do ativo."""
    if tipo in REGIME_FIIS:
        return "fiis"
    # ACAO, ETF, ETF_INTERNACIONAL, RENDA_FIXA -> regime acoes
    return "acoes"


def _calcular_ganho(preco_atual: float, preco_medio: float, quantidade: float) -> float:
    """Ganho (ou perda) de capital = (preco_atual - preco_medio) * quantidade."""
    return round((preco_atual - preco_medio) * quantidade, 2)


def _calcular_ganho_pct(preco_atual: float, preco_medio: float) -> float:
    """Percentual de ganho ou perda."""
    if preco_medio == 0:
        return 0.0
    return round(((preco_atual / preco_medio) - 1) * 100, 2)


def _fmt_reais(valor: float) -> str:
    """Formata valor monetario: R$ 1.234,56 ou -R$ 1.234,56."""
    if valor < 0:
        return f"-R$ {abs(valor):,.2f}"
    return f"R$ {valor:,.2f}"


# ---------------------------------------------------------------------------
# Funcao principal: coleta e calcula situacao tributaria
# ---------------------------------------------------------------------------

def compute_situacao_tributaria() -> dict:
    """
    Conecta ao banco de dados e calcula a situacao tributaria da carteira.

    Returns:
        dict com estrutura:
        {
            "acoes": {
                "prejuizos": [ {ticker, qtd, pm, preco_atual, prejuizo, prejuizo_pct, tipo}, ... ],
                "prejuizo_total": float,
                "lucros": [ {ticker, qtd, pm, preco_atual, lucro, ir_estimado, tipo}, ... ],
                "lucro_total": float,
                "ir_total_estimado": float,
                "prejuizo_compensavel": float,
                "lucro_liquido_pos_compensacao": float,
                "ir_pos_compensacao": float,
            },
            "fiis": { ... mesma estrutura ... },
            "resumo": {
                "ir_total_devido": float,
                "prejuizo_total_compensavel": float,
                "economia_fiscal_potencial": float,
                "posicoes_no_vermelho": int,
                "posicoes_no_verde": int,
            },
        }
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Query que junta posicoes, ativos e cotacao mais recente
    cur.execute("""
        SELECT
            p.ticker,
            p.quantidade_total,
            p.preco_medio,
            a.nome,
            a.tipo,
            c.fechamento AS preco_atual
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
        ORDER BY a.tipo, p.ticker
    """)

    rows = cur.fetchall()
    conn.close()

    # Estruturas para acumular por regime
    regimes = {
        "acoes": {"prejuizos": [], "lucros": [], "vendas_lucro_total": 0.0},
        "fiis":  {"prejuizos": [], "lucros": [], "vendas_lucro_total": 0.0},
    }

    total_no_vermelho = 0
    total_no_verde = 0

    for ticker, qtd, pm, nome, tipo, preco_atual in rows:
        qtd = float(qtd)
        pm = float(pm)
        preco_atual = float(preco_atual) if preco_atual else 0.0

        if preco_atual == 0:
            continue  # Sem cotacao, pular

        regime = _classificar_regime(tipo)
        ganho = _calcular_ganho(preco_atual, pm, qtd)
        ganho_pct = _calcular_ganho_pct(preco_atual, pm)

        entry = {
            "ticker": ticker,
            "qtd": qtd,
            "pm": pm,
            "preco_atual": preco_atual,
            "tipo": tipo,
        }

        if ganho < 0:
            # Prejuizo
            entry["prejuizo"] = ganho
            entry["prejuizo_pct"] = ganho_pct
            regimes[regime]["prejuizos"].append(entry)
            total_no_vermelho += 1
        elif ganho > 0:
            # Lucro
            entry["lucro"] = ganho
            entry["lucro_pct"] = ganho_pct
            regimes[regime]["lucros"].append(entry)
            regimes[regime]["vendas_lucro_total"] += preco_atual * qtd
            total_no_verde += 1
        # ganho == 0: neutro, ignorar

    # --- Processa cada regime ---
    resultado = {}

    for regime_key in ("acoes", "fiis"):
        r = regimes[regime_key]

        # Ordena prejuizos do maior (mais negativo) para o menor
        r["prejuizos"].sort(key=lambda x: x["prejuizo"])
        # Ordena lucros do maior para o menor
        r["lucros"].sort(key=lambda x: x["lucro"], reverse=True)

        prejuizo_total = round(sum(p["prejuizo"] for p in r["prejuizos"]), 2)
        lucro_total = round(sum(l["lucro"] for l in r["lucros"]), 2)

        # Calcula IR estimado
        if regime_key == "acoes":
            # Isencao: vendas ate R$ 20.000 no mes sao isentas
            # Se vendas totais das posicoes lucrativas > 20.000, IR = 15% sobre lucro
            vendas = r["vendas_lucro_total"]
            if vendas <= 20000.0:
                ir_total = 0.0
            else:
                ir_total = round(lucro_total * 0.15, 2)
        else:
            # FIIs: 20% sempre, sem isencao
            ir_total = round(lucro_total * 0.20, 2)

        # Calcula IR apos compensacao de prejuizos
        lucro_liquido = round(lucro_total + prejuizo_total, 2)  # prejuizo_total ja e negativo
        if lucro_liquido <= 0:
            lucro_liquido_pos = 0.0
            ir_pos = 0.0
        else:
            lucro_liquido_pos = lucro_liquido
            if regime_key == "acoes":
                vendas = r["vendas_lucro_total"]
                if vendas <= 20000.0:
                    ir_pos = 0.0
                else:
                    ir_pos = round(lucro_liquido_pos * 0.15, 2)
            else:
                ir_pos = round(lucro_liquido_pos * 0.20, 2)

        # Adiciona ir_estimado em cada entrada de lucro
        for l in r["lucros"]:
            if regime_key == "acoes" and r["vendas_lucro_total"] <= 20000.0:
                l["ir_estimado"] = 0.0
            elif regime_key == "acoes":
                l["ir_estimado"] = round(l["lucro"] * 0.15, 2)
            else:
                l["ir_estimado"] = round(l["lucro"] * 0.20, 2)

        resultado[regime_key] = {
            "prejuizos": r["prejuizos"],
            "prejuizo_total": prejuizo_total,
            "lucros": r["lucros"],
            "lucro_total": lucro_total,
            "ir_total_estimado": ir_total,
            "prejuizo_compensavel": prejuizo_total,  # sempre negativo (ou zero)
            "lucro_liquido_pos_compensacao": lucro_liquido_pos,
            "ir_pos_compensacao": ir_pos,
        }

    # --- Resumo consolidado ---
    ir_total_devido = round(
        resultado["acoes"]["ir_pos_compensacao"] +
        resultado["fiis"]["ir_pos_compensacao"],
        2,
    )
    prejuizo_total_compensavel = round(
        resultado["acoes"]["prejuizo_total"] +
        resultado["fiis"]["prejuizo_total"],
        2,
    )
    # Economia fiscal = IR sem compensacao - IR com compensacao
    ir_sem_compensacao = round(
        resultado["acoes"]["ir_total_estimado"] +
        resultado["fiis"]["ir_total_estimado"],
        2,
    )
    economia_fiscal = round(ir_sem_compensacao - ir_total_devido, 2)

    resultado["resumo"] = {
        "ir_total_devido": ir_total_devido,
        "prejuizo_total_compensavel": prejuizo_total_compensavel,
        "economia_fiscal_potencial": economia_fiscal,
        "posicoes_no_vermelho": total_no_vermelho,
        "posicoes_no_verde": total_no_verde,
        "ir_sem_compensacao": ir_sem_compensacao,
    }

    return resultado


# ---------------------------------------------------------------------------
# Funcao 2: Formatador para PDF (reportlab flowables)
# ---------------------------------------------------------------------------

def tributario_para_pdf(trib_data: dict, styles: dict = None) -> list:
    """
    Gera uma lista de flowables do ReportLab para a secao de Situacao Tributaria.

    Args:
        trib_data: dicionario retornado por compute_situacao_tributaria()
        styles: dicionario opcional com estilos personalizados.
                Chaves aceitas: h1, h2, body, small, muted.

    Returns:
        Lista de flowables (Paragraph, Spacer, Table) para inserir no PDF.
    """
    # --- Estilos padrao (podem ser sobrescritos pelo caller) ---
    default_styles = {
        "h1": ParagraphStyle(
            "TribH1",
            fontSize=16,
            textColor=COR["text"],
            spaceBefore=10,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "h2": ParagraphStyle(
            "TribH2",
            fontSize=12,
            textColor=COR["accent"],
            spaceBefore=8,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "TribBody",
            fontSize=9,
            textColor=COR["text"],
            leading=14,
            fontName="Helvetica",
        ),
        "small": ParagraphStyle(
            "TribSmall",
            fontSize=8,
            textColor=COR["muted"],
            leading=11,
            fontName="Helvetica",
        ),
        "muted": ParagraphStyle(
            "TribMuted",
            fontSize=8,
            textColor=COR["muted"],
            fontName="Helvetica-Oblique",
        ),
    }

    if styles:
        default_styles.update(styles)

    S = default_styles  # alias para conveniencia
    story = []

    # --- Cabecalho da secao ---
    story.append(Paragraph("Situacao Tributaria", S["h1"]))
    story.append(Paragraph(
        "Esta secao apresenta uma <b>estimativa do imposto de renda</b> que seria devido "
        "caso todas as posicoes com lucro fossem vendidas hoje, bem como os "
        "<b>prejuizos acumulados</b> que podem ser usados para compensar ganhos futuros. "
        "Os calculos seguem as regras vigentes da Receita Federal:",
        S["body"],
    ))
    story.append(Paragraph(
        "• <b>Acoes, ETFs e Renda Fixa:</b> 15% de IR sobre o ganho de capital. "
        "Vendas ate <b>R$ 20.000/mes</b> sao <b>isentas</b>.<br/>"
        "• <b>Fundos Imobiliarios (FIIs):</b> 20% de IR sobre o ganho de capital, "
        "<b>sem isencao</b>.<br/>"
        "• Prejuizos em acoes <b>compensam apenas ganhos em acoes</b>. "
        "Prejuizos em FIIs <b>compensam apenas ganhos em FIIs</b>.",
        S["small"],
    ))
    story.append(Spacer(1, 6))

    # --- Tabela 1: Prejuizos Compensaveis ---
    # Junta todos os prejuizos de ambos os regimes, ordenados do maior prejuizo
    todos_prejuizos = trib_data["acoes"]["prejuizos"] + trib_data["fiis"]["prejuizos"]
    todos_prejuizos.sort(key=lambda x: x["prejuizo"])  # mais negativo primeiro

    if todos_prejuizos:
        story.append(Paragraph("Prejuizos Compensaveis", S["h2"]))
        story.append(Paragraph(
            "Ativos com prejuizo que podem abater ganhos futuros no mesmo regime tributario.",
            S["muted"],
        ))
        story.append(Spacer(1, 3))

        t_header = ["Ativo", "Qtd", "PM", "Preco Atual", "Prejuizo R$", "Prejuizo %", "Regime"]
        t_data = [t_header]
        for p in todos_prejuizos:
            regime_label = "FIIs" if _classificar_regime(p["tipo"]) == "fiis" else "Acoes"
            color_prejuizo = COR["red"]
            t_data.append([
                Paragraph(f"<b>{p['ticker']}</b>", S["small"]),
                Paragraph(f"{p['qtd']:.0f}", S["small"]),
                Paragraph(f"R$ {p['pm']:.2f}", S["small"]),
                Paragraph(f"R$ {p['preco_atual']:.2f}", S["small"]),
                Paragraph(
                    f'<font color="{color_prejuizo}"><b>{_fmt_reais(p["prejuizo"])}</b></font>',
                    S["small"],
                ),
                Paragraph(
                    f'<font color="{color_prejuizo}"><b>{p["prejuizo_pct"]:+.1f}%</b></font>',
                    S["small"],
                ),
                Paragraph(regime_label, S["small"]),
            ])

        col_w = [18*mm, 12*mm, 22*mm, 24*mm, 24*mm, 22*mm, 18*mm]
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
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    # --- Tabela 2: IR Potencial sobre Posicoes com Lucro ---
    todos_lucros = trib_data["acoes"]["lucros"] + trib_data["fiis"]["lucros"]
    todos_lucros.sort(key=lambda x: x["lucro"], reverse=True)

    if todos_lucros:
        story.append(Paragraph("IR Potencial sobre Posicoes com Lucro", S["h2"]))
        story.append(Paragraph(
            "Estimativa do IR que seria devido se cada posicao lucrativa fosse vendida.",
            S["muted"],
        ))
        story.append(Spacer(1, 3))

        t_header = ["Ativo", "Qtd", "PM", "Preco Atual", "Lucro R$", "IR Estimado", "Regime"]
        t_data = [t_header]
        for p in todos_lucros:
            regime_label = "FIIs" if _classificar_regime(p["tipo"]) == "fiis" else "Acoes"
            color_lucro = COR["green"]
            t_data.append([
                Paragraph(f"<b>{p['ticker']}</b>", S["small"]),
                Paragraph(f"{p['qtd']:.0f}", S["small"]),
                Paragraph(f"R$ {p['pm']:.2f}", S["small"]),
                Paragraph(f"R$ {p['preco_atual']:.2f}", S["small"]),
                Paragraph(
                    f'<font color="{color_lucro}"><b>{_fmt_reais(p["lucro"])}</b></font>',
                    S["small"],
                ),
                Paragraph(f"R$ {p['ir_estimado']:.2f}", S["small"]),
                Paragraph(regime_label, S["small"]),
            ])

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
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COR["white"], HexColor("#F6F8FA")]),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    # --- Paragrafo de Resumo ---
    resumo = trib_data["resumo"]
    ir = resumo["ir_total_devido"]
    prejuizo = resumo["prejuizo_total_compensavel"]
    economia = resumo["economia_fiscal_potencial"]
    ir_sem = resumo.get("ir_sem_compensacao", ir + economia)

    cor_ir = COR["green"] if ir == 0 else COR["red"]
    cor_economia = COR["green"] if economia > 0 else COR["muted"]

    story.append(Paragraph("Resumo Tributario", S["h2"]))
    story.append(Paragraph(
        f"<b>IR total estimado:</b> "
        f'<font color="{cor_ir}"><b>R$ {ir:,.2f}</b></font> '
        f"(seria <b>R$ {ir_sem:,.2f}</b> sem compensacao de prejuizos)<br/>"
        f"<b>Prejuizo acumulado compensavel:</b> "
        f'<font color="{COR["red"]}"><b>{_fmt_reais(prejuizo)}</b></font><br/>'
        f"<b>Economia fiscal potencial:</b> "
        f'<font color="{cor_economia}"><b>R$ {economia:,.2f}</b></font><br/>'
        f"<b>Posicoes no vermelho:</b> {resumo['posicoes_no_vermelho']} | "
        f"<b>Posicoes no verde:</b> {resumo['posicoes_no_verde']}",
        S["body"],
    ))

    return story


# ---------------------------------------------------------------------------
# Funcao 3: Resumo para Telegram
# ---------------------------------------------------------------------------

def resumo_tributario_telegram(trib_data: dict) -> str:
    """
    Gera um texto curto (max ~300 caracteres) para envio via Telegram
    com os principais numeros da situacao tributaria.

    Args:
        trib_data: dicionario retornado por compute_situacao_tributaria()

    Returns:
        String formatada para Telegram.
    """
    resumo = trib_data["resumo"]
    acoes = trib_data["acoes"]
    fiis = trib_data["fiis"]

    ir = resumo["ir_total_devido"]
    prejuizo = resumo["prejuizo_total_compensavel"]
    economia = resumo["economia_fiscal_potencial"]
    red = resumo["posicoes_no_vermelho"]
    green = resumo["posicoes_no_verde"]

    linha1 = f"📊 IR Est: R$ {ir:,.2f} | Prej: {_fmt_reais(prejuizo)}"
    linha2 = f"💰 Economia fiscal: R$ {economia:,.2f}"
    linha3 = (
        f"🔴 {red} no vermelho | 🟢 {green} no verde | "
        f"Acoes IR: R$ {acoes['ir_pos_compensacao']:,.2f} | "
        f"FIIs IR: R$ {fiis['ir_pos_compensacao']:,.2f}"
    )

    return f"{linha1}\n{linha2}\n{linha3}"


# ---------------------------------------------------------------------------
# Teste rapido (executado apenas quando o modulo e rodado diretamente)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  MODULO TRIBUTARIO — Teste")
    print("=" * 60)

    # 1. Computar dados
    print("\n[1] Consultando banco de dados...")
    trib = compute_situacao_tributaria()

    # 2. Exibir resumo detalhado
    print("\n[2] Resumo:")
    r = trib["resumo"]
    print(f"    IR total devido:              R$ {r['ir_total_devido']:,.2f}")
    print(f"    IR sem compensacao:           R$ {r['ir_sem_compensacao']:,.2f}")
    print(f"    Prejuizo total compensavel:   {_fmt_reais(r['prejuizo_total_compensavel'])}")
    print(f"    Economia fiscal potencial:    R$ {r['economia_fiscal_potencial']:,.2f}")
    print(f"    Posicoes no vermelho:         {r['posicoes_no_vermelho']}")
    print(f"    Posicoes no verde:            {r['posicoes_no_verde']}")

    print("\n[3] Acoes:")
    a = trib["acoes"]
    print(f"    Lucro total:    R$ {a['lucro_total']:,.2f}")
    print(f"    Prejuizo total: {_fmt_reais(a['prejuizo_total'])}")
    print(f"    IR estimado:    R$ {a['ir_total_estimado']:,.2f}")
    print(f"    IR pos comp:    R$ {a['ir_pos_compensacao']:,.2f}")
    print(f"    Prejuizos ({len(a['prejuizos'])}):")
    for p in a["prejuizos"]:
        print(f"      {p['ticker']:8s} qtd={p['qtd']:5.0f} pm=R$ {p['pm']:.2f} "
              f"atual=R$ {p['preco_atual']:.2f} prejuizo={_fmt_reais(p['prejuizo'])} "
              f"({p['prejuizo_pct']:+.1f}%)")
    print(f"    Lucros ({len(a['lucros'])}):")
    for l in a["lucros"]:
        print(f"      {l['ticker']:8s} qtd={l['qtd']:5.0f} pm=R$ {l['pm']:.2f} "
              f"atual=R$ {l['preco_atual']:.2f} lucro={_fmt_reais(l['lucro'])} "
              f"IR=R$ {l['ir_estimado']:.2f}")

    print("\n[4] FIIs:")
    f = trib["fiis"]
    print(f"    Lucro total:    R$ {f['lucro_total']:,.2f}")
    print(f"    Prejuizo total: {_fmt_reais(f['prejuizo_total'])}")
    print(f"    IR estimado:    R$ {f['ir_total_estimado']:,.2f}")
    print(f"    IR pos comp:    R$ {f['ir_pos_compensacao']:,.2f}")
    print(f"    Prejuizos ({len(f['prejuizos'])}):")
    for p in f["prejuizos"]:
        print(f"      {p['ticker']:8s} qtd={p['qtd']:5.0f} pm=R$ {p['pm']:.2f} "
              f"atual=R$ {p['preco_atual']:.2f} prejuizo={_fmt_reais(p['prejuizo'])} "
              f"({p['prejuizo_pct']:+.1f}%)")
    print(f"    Lucros ({len(f['lucros'])}):")
    for l in f["lucros"]:
        print(f"      {l['ticker']:8s} qtd={l['qtd']:5.0f} pm=R$ {l['pm']:.2f} "
              f"atual=R$ {l['preco_atual']:.2f} lucro={_fmt_reais(l['lucro'])} "
              f"IR=R$ {l['ir_estimado']:.2f}")

    # 5. Telegram
    print("\n[5] Resumo Telegram:")
    print(resumo_tributario_telegram(trib))

    # 6. PDF flowables
    print("\n[6] PDF flowables gerados:", len(tributario_para_pdf(trib)), "elementos")

    print("\n✅ Teste concluido com sucesso!")