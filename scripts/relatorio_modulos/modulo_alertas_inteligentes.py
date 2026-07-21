#!/usr/bin/env python3
"""
Modulo de Alertas Inteligentes — Carteira Prof. Marcos
========================================================
Reformula a secao 6 do Relatorio Executivo, transformando alertas de
"variacao diaria crua" em alertas classificados e contextualizados.

4 Categorias:
  A. VARIACAO   — alertas existentes da tabela alertas (ultimos 7 dias)
  B. CONCENTRACAO — ativo > 20% da carteira por custo_total
  C. ALOCACAO    — classe desviou > 15pp do alvo estrategico
  D. EX-DIVIDENDO — queda do dia cruzada com proventos (data-com/pgto)

Exporta:
  - gerar_alertas_inteligentes() -> dict
  - alertas_para_pdf(alertas_data) -> list  (flowables ReportLab)
  - resumo_alertas_telegram(alertas_data) -> str
"""

import datetime

import psycopg2
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_utils import DB_CONFIG

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

# Alvos estrategicos de alocacao (mesmos do relatorio_executivo.py)
ALVOS = {
    "RENDA_FIXA": ("Renda Fixa", 20.0),
    "FII":        ("FIIs",       25.0),
    "ACAO":       ("Acoes",      35.0),
    "ETF":        ("ETFs BR",    10.0),
    "ETF_INTL":   ("ETF Intl",   10.0),
}

# Limites para disparar alertas
LIMITE_CONCENTRACAO_PCT = 20.0   # ativo > X% da carteira
LIMITE_ALOCACAO_GAP_PP = 15.0    # desvio > X pontos percentuais
LIMITE_QUEDA_PROVENTO_PCT = 1.0  # queda > X% no dia para cruzar com proventos
LIMITE_QUEDA_REAL_PCT = 2.0      # queda > X% sem provento = queda real
JANELA_PROVENTOS_DIAS = 5        # +/- dias ao redor de hoje para buscar proventos


# ═══════════════════════════════════════════════════════════════════
# Funcao principal: gera as 4 categorias de alertas
# ═══════════════════════════════════════════════════════════════════

def gerar_alertas_inteligentes() -> dict:
    """
    Conecta ao banco e retorna um dicionario com 4 categorias de alertas:

        {
            "variacao":     [...],   # lista de dicts — alertas existentes
            "concentracao": [...],   # ativos com peso > 20%
            "alocacao":     [...],   # classes com gap > 15pp
            "ex_dividendo": [...],   # quedas cruzadas com proventos
            "total":        N,       # soma dos tamanhos das 4 listas
        }

    Cada alerta e um dict com pelo menos: ticker, mensagem, categoria, cor.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    hoje = datetime.date.today()

    # ── A. Alertas de Variacao (existentes na tabela alertas) ──
    cur.execute("""
        SELECT ticker, tipo_alerta, mensagem, data_alerta
        FROM investimentos.alertas
        WHERE data_alerta >= NOW() - INTERVAL '7 days'
        ORDER BY data_alerta DESC
        LIMIT 10
    """)
    variacao = []
    for r in cur.fetchall():
        ticker, tipo, msg, dt = r
        dt_str = dt.strftime("%d/%m/%Y") if hasattr(dt, "strftime") else str(dt)[:10]
        variacao.append({
            "ticker":    ticker,
            "tipo":      tipo,
            "mensagem":  msg,
            "data":      dt_str,
            "categoria": "VARIACAO",
            "cor":       COR["accent"],
        })

    # ── B. Alerta de Concentracao (ativo > 20% da carteira) ──
    cur.execute("""
        SELECT ticker, custo_total,
               ROUND((custo_total * 100.0) / NULLIF((SELECT SUM(custo_total)
                                                      FROM investimentos.posicoes), 0), 2) AS pct
        FROM investimentos.posicoes
        WHERE custo_total > 0
        ORDER BY pct DESC
    """)
    concentracao = []
    for r in cur.fetchall():
        ticker, custo, pct = r
        pct = float(pct) if pct else 0.0
        if pct > LIMITE_CONCENTRACAO_PCT:
            concentracao.append({
                "ticker":    ticker,
                "pct":       pct,
                "custo":     float(custo),
                "mensagem":  (f"ATENCAO: {ticker} representa {pct:.1f}% da carteira "
                              f"— acima do limite de {LIMITE_CONCENTRACAO_PCT:.0f}%."),
                "categoria": "CONCENTRACAO",
                "cor":       COR["red"],
            })

    # ── C. Alerta de Alocacao (classe desviou > 15pp do alvo) ──
    # Primeiro, calcula a distribuicao atual por classe a partir de posicoes + ativos
    cur.execute("""
        SELECT a.tipo, SUM(p.custo_total) AS custo_classe
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        WHERE p.custo_total > 0
        GROUP BY a.tipo
    """)
    custo_por_tipo = {}
    for r in cur.fetchall():
        custo_por_tipo[r[0]] = float(r[1])

    custo_total = sum(custo_por_tipo.values()) if custo_por_tipo else 1.0

    alocacao = []
    for chave, (nome_amigavel, alvo_pct) in ALVOS.items():
        # Mapeia tipos do banco para chaves do ALVOS
        if chave == "ETF_INTL":
            tipo_banco = "ETF_INTERNACIONAL"
        else:
            tipo_banco = chave

        atual_val = custo_por_tipo.get(tipo_banco, 0.0)
        pct_atual = (atual_val / custo_total) * 100.0
        gap = pct_atual - alvo_pct

        if abs(gap) > LIMITE_ALOCACAO_GAP_PP:
            direcao = "acima" if gap > 0 else "abaixo"
            alocacao.append({
                "ticker":    nome_amigavel,
                "classe":    chave,
                "pct_atual": round(pct_atual, 1),
                "pct_alvo":  alvo_pct,
                "gap":       round(gap, 1),
                "direcao":   direcao,
                "mensagem":  (f"ALOCACAO: {nome_amigavel} estao {abs(gap):.1f}pp "
                              f"{direcao} do alvo (atual {pct_atual:.1f}% vs "
                              f"alvo {alvo_pct:.0f}%)."),
                "categoria": "ALOCACAO",
                "cor":       COR["orange"],
            })

    # ── D. Alerta de Ex-Dividendo (cruzamento queda vs proventos) ──
    # Busca cotacoes de HOJE com queda > LIMITE_QUEDA_PROVENTO_PCT
    cur.execute("""
        SELECT ticker, fechamento, variacao_pct
        FROM investimentos.cotacoes
        WHERE data = CURRENT_DATE
          AND variacao_pct IS NOT NULL
          AND variacao_pct < %s
    """, (-LIMITE_QUEDA_PROVENTO_PCT,))
    quedas_hoje = {r[0]: {"preco": float(r[1]) if r[1] else 0.0,
                           "var": float(r[2]) if r[2] else 0.0}
                   for r in cur.fetchall()}

    # Busca proventos com data_com_estimada nos proximos JANELA dias
    # ou data_pgto nos ultimos JANELA dias
    cur.execute("""
        SELECT ticker, data_pgto, data_com_estimada, valor, tipo
        FROM investimentos.proventos
        WHERE (data_com_estimada BETWEEN CURRENT_DATE - INTERVAL '%s days'
                                     AND CURRENT_DATE + INTERVAL '%s days')
           OR (data_pgto BETWEEN CURRENT_DATE - INTERVAL '%s days'
                             AND CURRENT_DATE + INTERVAL '%s days')
    """, (JANELA_PROVENTOS_DIAS, JANELA_PROVENTOS_DIAS,
          JANELA_PROVENTOS_DIAS, JANELA_PROVENTOS_DIAS))
    proventos_por_ticker = {}
    for r in cur.fetchall():
        ticker, dt_pgto, dt_com, valor, tipo = r
        proventos_por_ticker.setdefault(ticker, []).append({
            "data_pgto":        dt_pgto.strftime("%d/%m") if hasattr(dt_pgto, "strftime") else str(dt_pgto)[:5],
            "data_com_estimada": dt_com.strftime("%d/%m") if dt_com and hasattr(dt_com, "strftime") else (str(dt_com)[:5] if dt_com else "N/D"),
            "valor":            float(valor) if valor else 0.0,
            "tipo":             tipo or "",
        })

    ex_dividendo = []
    for ticker, dados_queda in quedas_hoje.items():
        var_pct = dados_queda["var"]
        provs = proventos_por_ticker.get(ticker, [])

        if provs:
            # Queda com provento — provavelmente data-com
            prov = provs[0]  # primeiro provento encontrado
            ex_dividendo.append({
                "ticker":    ticker,
                "variacao":  var_pct,
                "tipo":      "QUEDA_COM_PROVENTO",
                "provento":  prov,
                "mensagem":  (f"QUEDA COM PROVENTO: {ticker} caiu {var_pct:+.1f}%, "
                              f"mas distribuiu R$ {prov['valor']:.2f}/provento "
                              f"({prov['tipo']}) — queda real menor."),
                "categoria": "EX_DIVIDENDO",
                "cor":       COR["yellow"],
            })
        elif abs(var_pct) > LIMITE_QUEDA_REAL_PCT:
            # Queda real — sem justificativa de provento
            ex_dividendo.append({
                "ticker":    ticker,
                "variacao":  var_pct,
                "tipo":      "QUEDA_REAL",
                "provento":  None,
                "mensagem":  (f"QUEDA REAL: {ticker} caiu {var_pct:+.1f}% "
                              f"sem justificativa de provento."),
                "categoria": "EX_DIVIDENDO",
                "cor":       COR["yellow"],
            })

    conn.close()

    total = len(variacao) + len(concentracao) + len(alocacao) + len(ex_dividendo)

    return {
        "variacao":     variacao,
        "concentracao": concentracao,
        "alocacao":     alocacao,
        "ex_dividendo": ex_dividendo,
        "total":        total,
    }


# ═══════════════════════════════════════════════════════════════════
# Formatador para PDF (ReportLab flowables)
# ═══════════════════════════════════════════════════════════════════

def alertas_para_pdf(alertas_data: dict) -> list:
    """
    Recebe o dict retornado por gerar_alertas_inteligentes() e retorna
    uma lista de flowables do ReportLab (Paragraph, Spacer, etc.)
    prontos para serem inseridos no PDF.

    Agrupados por categoria com headers coloridos:
      VARIACAO     -> COR["accent"] (azul)
      CONCENTRACAO -> COR["red"]    (vermelho)
      ALOCACAO     -> COR["orange"] (laranja)
      EX_DIVIDENDO -> COR["yellow"] (amarelo/ocre)
    """
    # Estilos locais para os alertas (independentes do estilo do script principal)
    style_header = ParagraphStyle(
        "AlertaHeader",
        fontSize=11,
        fontName="Helvetica-Bold",
        leading=14,
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
    )
    style_item = ParagraphStyle(
        "AlertaItem",
        fontSize=9,
        fontName="Helvetica",
        leading=12,
        textColor=COR["text"],
        leftIndent=4 * mm,
        spaceAfter=1 * mm,
    )
    style_item_destaque = ParagraphStyle(
        "AlertaItemDestaque",
        parent=style_item,
        fontName="Helvetica-Bold",
    )

    elementos = []

    # Categorias na ordem desejada, com label e cor
    categorias = [
        ("variacao",     "📊 Variação (últimos 7 dias)",  COR["accent"]),
        ("concentracao", "⚠️  Concentração",               COR["red"]),
        ("alocacao",     "📐 Alocação vs Alvo",            COR["orange"]),
        ("ex_dividendo", "💸 Ex-Dividendo / Quedas",       COR["yellow"]),
    ]

    for chave, titulo, cor in categorias:
        lista = alertas_data.get(chave, [])
        if not lista:
            continue

        # Header da categoria
        header = ParagraphStyle(
            f"AlertaHeader_{chave}",
            parent=style_header,
            textColor=cor,
        )
        elementos.append(Paragraph(titulo, header))

        # Itens
        for item in lista:
            msg = item.get("mensagem", "")
            # Item de concentracao e alocacao em destaque (bold)
            if chave in ("concentracao", "alocacao"):
                elementos.append(Paragraph(f"• {msg}", style_item_destaque))
            else:
                # Para variacao, inclui a data
                if chave == "variacao":
                    data_str = item.get("data", "")
                    elementos.append(Paragraph(
                        f"• <b>{data_str}</b> — <b>{item['ticker']}</b>: {msg}",
                        style_item))
                else:
                    elementos.append(Paragraph(f"• {msg}", style_item))

        elementos.append(Spacer(1, 2 * mm))

    return elementos


# ═══════════════════════════════════════════════════════════════════
# Formatador para Telegram (resumo curto)
# ═══════════════════════════════════════════════════════════════════

def resumo_alertas_telegram(alertas_data: dict) -> str:
    """
    Retorna texto curto (max ~500 chars) com resumo dos alertas mais
    importantes, adequado para envio via Telegram.
    Prioriza: CONCENTRACAO > ALOCACAO > EX_DIVIDENDO > VARIACAO.
    """
    linhas = []
    linhas.append("🔔 <b>Alertas Inteligentes</b>")

    total = alertas_data.get("total", 0)
    if total == 0:
        linhas.append("✅ Nenhum alerta ativo no momento.")
        return "\n".join(linhas)

    # 1. Concentracao — mais critico
    conc = alertas_data.get("concentracao", [])
    if conc:
        linhas.append("")
        linhas.append("⚠️ <b>Concentração:</b>")
        for item in conc:
            linhas.append(f"  • {item['ticker']}: {item['pct']:.1f}% da carteira")

    # 2. Alocacao
    aloc = alertas_data.get("alocacao", [])
    if aloc:
        linhas.append("")
        linhas.append("📐 <b>Alocação:</b>")
        for item in aloc:
            emoji = "🔴" if item["gap"] > 0 else "🟢"
            linhas.append(f"  {emoji} {item['ticker']}: {item['gap']:+.1f}pp "
                          f"(atual {item['pct_atual']:.0f}% vs alvo {item['pct_alvo']:.0f}%)")

    # 3. Ex-Dividendo
    exd = alertas_data.get("ex_dividendo", [])
    if exd:
        linhas.append("")
        linhas.append("💸 <b>Quedas:</b>")
        for item in exd:
            if item.get("tipo") == "QUEDA_COM_PROVENTO":
                linhas.append(f"  • {item['ticker']}: {item['variacao']:+.1f}% "
                              f"(com provento R${item['provento']['valor']:.2f})")
            else:
                linhas.append(f"  • {item['ticker']}: {item['variacao']:+.1f}% "
                              f"(queda real)")

    # 4. Variacao — apenas contagem
    var = alertas_data.get("variacao", [])
    if var:
        linhas.append("")
        linhas.append(f"📊 {len(var)} alerta(s) de variação nos últimos 7 dias.")

    # Monta o texto final e trunca se necessario (~500 chars)
    texto = "\n".join(linhas)
    if len(texto) > 500:
        # Trunca no ultimo \n antes de 500 chars
        texto = texto[:497] + "..."

    return texto


# ═══════════════════════════════════════════════════════════════════
# Execucao direta (teste)
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("MODULO DE ALERTAS INTELIGENTES — Teste")
    print("=" * 60)

    try:
        alertas = gerar_alertas_inteligentes()
    except Exception as e:
        print(f"\n❌ Erro ao conectar/consultar banco: {e}")
        import sys
        sys.exit(1)

    print(f"\nTotal de alertas: {alertas['total']}")
    print(f"  Variacao:     {len(alertas['variacao'])}")
    print(f"  Concentracao: {len(alertas['concentracao'])}")
    print(f"  Alocacao:     {len(alertas['alocacao'])}")
    print(f"  Ex-Dividendo: {len(alertas['ex_dividendo'])}")

    # Exibe detalhes
    for cat, titulo in [("variacao", "VARIACAO"), ("concentracao", "CONCENTRACAO"),
                         ("alocacao", "ALOCACAO"), ("ex_dividendo", "EX-DIVIDENDO")]:
        items = alertas[cat]
        if items:
            print(f"\n── {titulo} ({len(items)}) ──")
            for item in items:
                print(f"  • {item['mensagem']}")

    # Teste PDF flowables
    print("\n── PDF Flowables (gerados) ──")
    flowables = alertas_para_pdf(alertas)
    print(f"  {len(flowables)} elementos gerados para o PDF.")

    # Teste Telegram
    print("\n── Resumo Telegram ──")
    print(resumo_alertas_telegram(alertas))

    print("\n✅ Modulo testado com sucesso!")