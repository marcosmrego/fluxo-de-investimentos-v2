#!/usr/bin/env python3
"""
Modulo de Alocacao Avancada com IR Estimado e Rebalanceamento por Fluxo
========================================================================
Estende a secao 1B do Relatorio Executivo adicionando:
  - Valores em R$ para vender/comprar de cada classe
  - Estimativa de IR sobre ganho de capital na venda
  - Sugestao de rebalanceamento por fluxo (ordem de prioridade dos proximos aportes)

Integracao: importado por relatorio_executivo.py ou usado standalone.
Autor: Hermes AI Agent
Data: 2026-07-19
"""

import sys
import logging
from typing import Optional

import psycopg2

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_utils import DB_CONFIG

# ── Cores (mesmo tema CLEAN do relatorio principal) ──────────────
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

# ── Alocacao Alvo (hardcoded, mesma do relatorio principal) ─────
ALVO_CLASSES = {
    "RENDA_FIXA": ("Renda Fixa", 20.0, "#8250DF"),
    "FII":        ("FIIs",       25.0, "#0969DA"),
    "ACAO":       ("Acoes",      35.0, "#1A7F37"),
    "ETF":        ("ETFs BR",    10.0, "#9A6700"),
    "ETF_INTL":   ("ETF Intl",   10.0, "#BC4C00"),
}

# ── Constantes de IR ─────────────────────────────────────────────
IR_FII_ALIQUOTA = 0.20       # FIIs: 20% sobre lucro, sem isencao
IR_ACAO_ALIQUOTA = 0.15      # Acoes/ETFs/Renda Fixa: 15% sobre lucro
IR_ISENCAO_MENSAL = 20000.0  # Isencao para vendas < R$ 20.000/mes (acoes)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    FUNCOES PURAS (CORE)                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def _normalizar_tipo(tipo: str) -> str:
    """
    Normaliza o campo 'tipo' do banco para a chave usada em ALVO_CLASSES.
    ETF_INTERNACIONAL -> ETF_INTL, RENDA_FIXA -> RENDA_FIXA, etc.
    """
    if tipo == "ETF_INTERNACIONAL":
        return "ETF_INTL"
    return tipo


def _agrupar_ativos_por_classe(posicoes: list) -> dict:
    """
    Agrupa os ativos por classe normalizada.
    Retorna: dict[classe] = [ativos_da_classe]
    Cada ativo mantem todos os campos originais.
    """
    grupos = {}
    for p in posicoes:
        classe = _normalizar_tipo(p.get("tipo", ""))
        if classe not in grupos:
            grupos[classe] = []
        grupos[classe].append(p)
    return grupos


def _calcular_ir_por_ativo(ativo: dict, qtd_excedente: float, classe: str) -> float:
    """
    Calcula o IR estimado para venda da quantidade excedente de UM ativo.

    Parametros:
        ativo: dict com preco (preco_atual), pm (preco_medio), qtd, etc.
        qtd_excedente: quantidade a vender
        classe: chave da classe (RENDA_FIXA, FII, ACAO, ETF, ETF_INTL)

    Retorna:
        float: valor estimado de IR a pagar
    """
    preco_atual = float(ativo.get("preco", 0) or 0)
    preco_medio = float(ativo.get("pm", 0) or 0)

    if qtd_excedente <= 0 or preco_atual <= preco_medio:
        # Sem lucro = sem IR
        return 0.0

    lucro = (preco_atual - preco_medio) * qtd_excedente

    # FIIs: 20% sobre lucro, sempre (sem isencao)
    if classe == "FII":
        return round(lucro * IR_FII_ALIQUOTA, 2)

    # Acoes, ETFs, ETFs Intl, Renda Fixa: 15% com isencao se vendas < R$ 20.000
    # Para simplificar: consideramos que toda venda do mes ocorre junta.
    # O valor total da venda = preco_atual * qtd_excedente
    valor_venda = preco_atual * qtd_excedente
    if valor_venda <= IR_ISENCAO_MENSAL:
        return 0.0  # Isento

    return round(lucro * IR_ACAO_ALIQUOTA, 2)


def _calcular_ir_classe(ativos: list, gap_pct: float, classe: str) -> float:
    """
    Calcula o IR total estimado para vender o excesso de uma classe inteira.

    Distribui a venda proporcionalmente entre os ativos da classe
    e soma o IR de cada um.
    """
    if gap_pct <= 0:
        return 0.0  # Nao ha excesso, nao ha venda

    ir_total = 0.0
    qtd_total_classe = sum(float(a.get("qtd", 0)) for a in ativos)

    if qtd_total_classe == 0:
        return 0.0

    for ativo in ativos:
        qtd_ativo = float(ativo.get("qtd", 0))
        # Proporcao do ativo na classe
        proporcao = qtd_ativo / qtd_total_classe
        # Quantidade excedente proporcional ao gap
        qtd_excedente = qtd_ativo * (gap_pct / 100.0)
        ir_total += _calcular_ir_por_ativo(ativo, qtd_excedente, classe)

    return round(ir_total, 2)


def _calcular_valor_mercado_classe(ativos: list) -> float:
    """Soma do valor de mercado (preco_atual * qtd) de todos os ativos da classe."""
    total = 0.0
    for a in ativos:
        preco = float(a.get("preco", 0) or 0)
        qtd = float(a.get("qtd", 0))
        total += preco * qtd
    return round(total, 2)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                   FUNCAO PRINCIPAL (1)                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def compute_alocacao_avancada(posicoes: list, custo_total: float) -> list:
    """
    Calcula alocacao avancada estendendo _compute_alocacao().

    Parametros:
        posicoes: lista de dicts (formato de get_data() do relatorio_executivo.py)
                  Campos esperados: ticker, qtd, pm, custo, preco, lucro, rent, nome, tipo, setor
        custo_total: float — custo total da carteira

    Retorna:
        list de dicts, cada um com:
            classe, pct_atual, pct_alvo, gap, status, emoji, cor, atual_val,
            valor_mercado, gap_rs, ir_estimado_venda, acao_rebalanceamento, prioridade_aporte
    """
    # Agrupa ativos por classe normalizada
    grupos = _agrupar_ativos_por_classe(posicoes)

    # Calcula valor atual (custo) por classe
    atual_map = {}
    for classe, ativos in grupos.items():
        atual_map[classe] = sum(float(a.get("custo", 0)) for a in ativos)

    rows = []
    for chave, (nome, alvo, cor) in ALVO_CLASSES.items():
        atual_val = atual_map.get(chave, 0.0)
        pct_atual = (atual_val / custo_total * 100.0) if custo_total > 0 else 0.0
        gap = pct_atual - alvo

        # Status e emoji
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

        # Valor de mercado da classe
        ativos_classe = grupos.get(chave, [])
        valor_mercado = _calcular_valor_mercado_classe(ativos_classe)

        # Gap em reais
        gap_rs = round((gap / 100.0) * custo_total, 2)

        # IR estimado de venda (apenas se gap > 0, ou seja, acima do alvo)
        ir_estimado = 0.0
        if gap > 0:
            ir_estimado = _calcular_ir_classe(ativos_classe, gap, chave)
        else:
            ir_estimado = 0.0

        # Acao de rebalanceamento
        acao = _gerar_acao_rebalanceamento(nome, gap_rs, gap, status)

        # Armazena gap_pct para uso na prioridade
        rows.append({
            "classe": nome,
            "chave": chave,
            "pct_atual": round(pct_atual, 2),
            "pct_alvo": alvo,
            "gap": round(gap, 2),
            "status": status,
            "emoji": emoji,
            "cor": cor,
            "atual_val": round(atual_val, 2),
            "valor_mercado": valor_mercado,
            "gap_rs": gap_rs,
            "ir_estimado_venda": ir_estimado,
            "acao_rebalanceamento": acao,
            "_ativos": ativos_classe,  # interno, removido na saida publica
        })

    # Calcula prioridade de aporte (ranking 1-5)
    # Classes abaixo do alvo tem maior prioridade; quanto mais abaixo, mais prioritario
    rows = _calcular_prioridades(rows)

    # Remove campos internos antes de retornar
    for r in rows:
        r.pop("_ativos", None)
        r.pop("chave", None)

    return rows


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    FUNCOES AUXILIARES                          ║
# ╚══════════════════════════════════════════════════════════════════╝

def _gerar_acao_rebalanceamento(nome: str, gap_rs: float, gap_pct: float, status: str) -> str:
    """
    Gera um texto descritivo da acao de rebalanceamento.

    Exemplos:
        "Vender ~R$ 5.129 para reduzir aos 25% alvo"
        "Investir R$ 8.300 para atingir os 20% alvo"
    """
    if abs(gap_rs) < 1.0:
        return f"Manter — dentro da faixa alvo"

    if gap_rs > 0:
        # Acima do alvo: vender/reduzir
        return f"Vender ~R$ {abs(gap_rs):,.0f} para reduzir ao alvo de {ALVO_CLASSES.get(_nome_para_chave(nome), (None, 0))[1]:.0f}%"
    else:
        # Abaixo do alvo: comprar/aumentar
        return f"Investir R$ {abs(gap_rs):,.0f} para atingir o alvo de {ALVO_CLASSES.get(_nome_para_chave(nome), (None, 0))[1]:.0f}%"


def _nome_para_chave(nome: str) -> Optional[str]:
    """Converte nome de exibicao para chave interna."""
    mapa = {
        "Renda Fixa": "RENDA_FIXA",
        "FIIs": "FII",
        "Acoes": "ACAO",
        "ETFs BR": "ETF",
        "ETF Intl": "ETF_INTL",
    }
    return mapa.get(nome)


def _calcular_prioridades(rows: list) -> list:
    """
    Atribui prioridade de aporte (1 = maxima prioridade) para cada classe.

    Regra: classes abaixo do alvo recebem prioridade mais alta (menor numero).
    Classes acima do alvo recebem prioridade baixa (prioridade 5 = nao aportar).
    Empatadas: maior gap absoluto primeiro.
    """
    # Separa abaixo e acima do alvo
    abaixo = [r for r in rows if r["gap"] < -0.5]   # Abaixo do alvo
    neutro = [r for r in rows if -0.5 <= r["gap"] <= 0.5]  # Dentro da faixa
    acima = [r for r in rows if r["gap"] > 0.5]    # Acima do alvo

    # Ordena abaixo: maior gap negativo primeiro (mais longe do alvo = mais prioritario)
    abaixo.sort(key=lambda r: r["gap"])  # gap negativo → menor primeiro

    # Ordena neutro: mais proximo de zero primeiro
    neutro.sort(key=lambda r: abs(r["gap"]))

    # Ordena acima: maior gap positivo primeiro
    acima.sort(key=lambda r: -r["gap"])

    rank = 1
    for r in abaixo:
        r["prioridade_aporte"] = rank
        rank += 1
    for r in neutro:
        r["prioridade_aporte"] = rank
        rank += 1
    for r in acima:
        r["prioridade_aporte"] = rank
        rank += 1

    return rows


# ╔══════════════════════════════════════════════════════════════════╗
# ║                FUNCAO PARA TABELA PDF (2)                      ║
# ╚══════════════════════════════════════════════════════════════════╝

def tabela_alocacao_avancada_para_pdf(aloc_data: list) -> list:
    """
    Retorna dados formatados para tabela do reportlab.

    Colunas: Classe | % Atual | % Alvo | Gap R$ | Acao | IR Est. | Prioridade

    Parametros:
        aloc_data: saida de compute_alocacao_avancada()

    Retorna:
        list de listas, primeira linha = cabecalho
    """
    cabecalho = ["Classe", "% Atual", "% Alvo", "Gap R$", "Acao", "IR Est.", "Prior."]
    linhas = [cabecalho]

    for r in aloc_data:
        # Formata gap_rs com sinal
        gap_str = f"R$ {r['gap_rs']:+,.0f}"

        # Formata IR estimado
        if r["ir_estimado_venda"] > 0:
            ir_str = f"R$ {r['ir_estimado_venda']:,.2f}"
        else:
            ir_str = "—"

        linhas.append([
            r["classe"],
            f"{r['pct_atual']:.1f}%",
            f"{r['pct_alvo']:.0f}%",
            gap_str,
            r["acao_rebalanceamento"],
            ir_str,
            str(r["prioridade_aporte"]),
        ])

    return linhas


# ╔══════════════════════════════════════════════════════════════════╗
# ║            FUNCAO PARA PARAGRAFO HTML (3)                      ║
# ╚══════════════════════════════════════════════════════════════════╝

def paragrafo_rebalanceamento_fluxo(aloc_data: list, aporte_mensal_min: float = 1000.0,
                                     aporte_mensal_max: float = 2000.0) -> str:
    """
    Retorna texto HTML para Paragraph do reportlab com a estrategia de
    convergencia por aportes.

    Parametros:
        aloc_data: saida de compute_alocacao_avancada()
        aporte_mensal_min: valor minimo do aporte tipico (default R$ 1.000)
        aporte_mensal_max: valor maximo do aporte tipico (default R$ 2.000)

    Retorna:
        str: HTML pronto para Paragraph do reportlab
    """
    # Filtra apenas classes abaixo do alvo e ordena por prioridade
    abaixo = [r for r in aloc_data if r["gap"] < -0.5]
    abaixo.sort(key=lambda r: r["prioridade_aporte"])

    if not abaixo:
        return (
            "<b>✅ Carteira balanceada!</b> Todas as classes estao dentro da faixa alvo. "
            "Mantenha os aportes distribuidos conforme a alocacao estrategica."
        )

    # Calcula rateio proporcional ao gap
    total_gap_rs = sum(abs(r["gap_rs"]) for r in abaixo)
    if total_gap_rs == 0:
        total_gap_rs = 1  # evita divisao por zero

    linhas = []
    linhas.append(
        "<b>🔁 Estrategia de Convergencia por Aportes</b><br/>"
        f"Considerando aporte mensal tipico de <b>R$ {aporte_mensal_min:,.0f} "
        f"a R$ {aporte_mensal_max:,.0f}</b>. "
        "Foco total nas classes abaixo do alvo ate reequilibrar.<br/><br/>"
    )

    for r in abaixo:
        proporcao = abs(r["gap_rs"]) / total_gap_rs
        valor_sugerido = aporte_mensal_min + (aporte_mensal_max - aporte_mensal_min) * proporcao
        valor_sugerido = round(valor_sugerido, -2)  # arredonda para centena mais proxima

        # Estima meses para fechar o gap com esse aporte
        if valor_sugerido > 0:
            meses = abs(r["gap_rs"]) / valor_sugerido
            meses_str = f"{meses:.1f} meses" if meses < 24 else f"{meses/12:.1f} anos"
        else:
            meses_str = "—"

        emoji_prio = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r["prioridade_aporte"], f"#{r['prioridade_aporte']}")

        linhas.append(
            f"<b>{emoji_prio} {r['classe']}</b> (prioridade {r['prioridade_aporte']}): "
            f"sugerido <b>R$ {valor_sugerido:,.0f}/mes</b> "
            f"ate atingir {r['pct_alvo']:.0f}% "
            f"(gap atual: R$ {abs(r['gap_rs']):,.0f}, "
            f"estimativa: ~{meses_str})<br/>"
        )

    # Nota sobre as classes acima do alvo
    acima = [r for r in aloc_data if r["gap"] > 0.5]
    if acima:
        acima.sort(key=lambda r: r["prioridade_aporte"])
        linhas.append("<br/><b>⚠️ NAO aportar em:</b> ")
        linhas.append(", ".join(r["classe"] for r in acima))
        linhas.append(" (acima do alvo — venda ou aguardar diluicao natural)")

    return "".join(linhas)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    CONSULTA AO BANCO                           ║
# ╚══════════════════════════════════════════════════════════════════╝

def carregar_posicoes(db_config: dict = None) -> tuple:
    """
    Conecta ao banco e carrega as posicoes com cotacao mais recente.

    Parametros:
        db_config: dict com host, port, user, password, dbname.
                   Se None, usa DB_CONFIG padrao.

    Retorna:
        tuple (posicoes, custo_total):
            posicoes: list de dicts
            custo_total: float
    """
    cfg = db_config or DB_CONFIG
    conn = psycopg2.connect(**cfg)
    cur = conn.cursor()

    cur.execute("""
        SELECT p.ticker, p.quantidade_total, p.preco_medio, p.custo_total,
               c.fechamento as preco_atual, a.nome, a.tipo, a.setor
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
        qtd = float(r[1])
        pm = float(r[2])
        custo = float(r[3])
        preco = float(r[4]) if r[4] else 0.0
        lucro = round((preco - pm) * qtd, 2) if preco else 0.0
        rent = round(((preco / pm) - 1) * 100, 2) if pm > 0 and preco > 0 else 0.0

        posicoes.append({
            "ticker": r[0],
            "qtd": qtd,
            "pm": pm,
            "custo": custo,
            "preco": preco,
            "lucro": lucro,
            "rent": rent,
            "nome": r[5],
            "tipo": r[6],
            "setor": r[7] or "",
        })

    custo_total = sum(p["custo"] for p in posicoes)

    conn.close()

    return posicoes, custo_total


# ╔══════════════════════════════════════════════════════════════════╗
# ║                FORMATACAO PARA TERMINAL                        ║
# ╚══════════════════════════════════════════════════════════════════╝

def _formatar_relatorio_terminal(aloc_data: list, custo_total: float) -> str:
    """
    Formata os resultados para exibicao no terminal (modo standalone).
    Retorna string pronta para print.
    """
    linhas = []
    sep = "=" * 100
    subsep = "-" * 100

    linhas.append(sep)
    linhas.append("  ALOCACAO AVANCADA — com IR Estimado e Rebalanceamento por Fluxo")
    linhas.append(sep)
    linhas.append(f"  Custo Total da Carteira: R$ {custo_total:,.2f}")
    linhas.append("")

    # Tabela resumo
    cabecalho = f"  {'Classe':<14} {'% Atual':>8} {'% Alvo':>7} {'Gap R$':>14} {'Status':<10} {'IR Est.':>14} {'Prior.':>7}"
    linhas.append(cabecalho)
    linhas.append(f"  {'-'*14} {'-'*8} {'-'*7} {'-'*14} {'-'*10} {'-'*14} {'-'*7}")

    for r in aloc_data:
        gap_str = f"R$ {r['gap_rs']:+,.0f}"
        ir_str = f"R$ {r['ir_estimado_venda']:,.2f}" if r["ir_estimado_venda"] > 0 else "—"
        linhas.append(
            f"  {r['classe']:<14} {r['pct_atual']:>7.1f}% {r['pct_alvo']:>6.0f}% "
            f"{gap_str:>14} {r['emoji']+' '+r['status']:<10} {ir_str:>14} {r['prioridade_aporte']:>7}"
        )

    linhas.append("")
    linhas.append(subsep)
    linhas.append("  DETALHES — Acao de Rebalanceamento")
    linhas.append(subsep)
    for r in aloc_data:
        linhas.append(f"  {r['emoji']} {r['classe']}: {r['acao_rebalanceamento']}")

    linhas.append("")
    linhas.append(subsep)
    linhas.append("  ESTRATEGIA DE CONVERGENCIA POR APORTES")
    linhas.append(subsep)

    # Usa a funcao de paragrafo e extrai texto simples do HTML
    html = paragrafo_rebalanceamento_fluxo(aloc_data)

    # Converte HTML basico para texto terminal
    import re as _re
    texto = html
    texto = _re.sub(r'<br\s*/?>', '\n  ', texto)
    texto = _re.sub(r'<b>(.*?)</b>', r'\1', texto)
    texto = _re.sub(r'<[^>]+>', '', texto)
    texto = texto.replace('&nbsp;', ' ')

    for line in texto.split('\n'):
        if line.strip():
            linhas.append(f"  {line.strip()}")

    linhas.append("")
    linhas.append(sep)
    linhas.append("  Gerado por modulo_alocacao_ir.py — Hermes AI Agent")
    linhas.append(sep)

    return "\n".join(linhas)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    BLOCO MAIN (standalone)                     ║
# ╚══════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    print("Conectando ao banco de dados...")
    try:
        posicoes, custo_total = carregar_posicoes()
        print(f"OK: {len(posicoes)} posicoes carregadas. Custo total: R$ {custo_total:,.2f}")
    except Exception as e:
        print(f"ERRO ao conectar ao banco: {e}")
        print("Verifique a conectividade com {host}:{port}/{dbname}".format(**DB_CONFIG))
        sys.exit(1)

    print("\nCalculando alocacao avancada...")
    aloc_data = compute_alocacao_avancada(posicoes, custo_total)

    print(_formatar_relatorio_terminal(aloc_data, custo_total))

    # Tambem imprime a saida da tabela para PDF
    print("\n--- Dados para tabela PDF ---")
    tabela = tabela_alocacao_avancada_para_pdf(aloc_data)
    for row in tabela:
        print(" | ".join(str(c) for c in row))

    print("\n--- Paragrafo HTML para PDF ---")
    print(paragrafo_rebalanceamento_fluxo(aloc_data))