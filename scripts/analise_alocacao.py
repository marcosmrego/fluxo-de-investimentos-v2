#!/usr/bin/env python3
"""
analise_alocacao.py — Analisa distribuicao atual da carteira e gera
proposta de alocacao estrategica com plano de migracao.
"""

import psycopg2
from datetime import date
from collections import defaultdict

from db_utils import DB_CONFIG

# ── Matriz de alocacao proposta ─────────────────────────────────────
# Perfil: crescimento moderado, foco em renda passiva + crescimento

ALOCACAO_ALVO = {
    "RENDA_FIXA":      {"alvo": 20.0, "desc": "Reserva de emergencia + protecao", "exemplos": "Tesouro Selic, CDB 100% CDI, LCI/LCA"},
    "FII":             {"alvo": 25.0, "desc": "Renda mensal passiva", "exemplos": "Diversificar setores: logistica, papel, hibrido, shopping, lajes"},
    "ACAO":            {"alvo": 35.0, "desc": "Crescimento + dividendos", "exemplos": "Setores perenes: bancos, energia, saneamento, seguros"},
    "ETF_BR":          {"alvo": 10.0, "desc": "Exposicao ampla ao mercado BR", "exemplos": "BOVA11/DIVO11/IDIV11"},
    "ETF_INTL":        {"alvo": 10.0, "desc": "Diversificacao geografica", "exemplos": "IVVB11/WRLD11/ACWI11"},
}


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # Buscar distribuicao atual
    cur.execute("""
        SELECT 
            CASE 
                WHEN a.tipo = 'ETF_INTERNACIONAL' THEN 'ETF_INTL'
                WHEN a.tipo = 'ETF' THEN 'ETF_BR'
                WHEN a.tipo = 'RENDA_FIXA' THEN 'RENDA_FIXA'
                ELSE a.tipo
            END as classe,
            COUNT(*) as ativos,
            ROUND(SUM(p.custo_total)::numeric, 2) as custo_total,
            ROUND(AVG(p.preco_medio)::numeric, 2) as pm_medio
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        GROUP BY 1
        ORDER BY SUM(p.custo_total) DESC
    """)
    rows = cur.fetchall()

    # Calcular totais
    total_brl = sum(float(r[2]) for r in rows if r[0] != 'ETF_INTL')
    total_usd = sum(float(r[2]) for r in rows if r[0] == 'ETF_INTL')

    atual = {}
    for classe, qtd, custo, pm in rows:
        atual[classe] = {"qtd": qtd, "custo": float(custo), "pm_medio": float(pm) if pm else 0}

    # ── Relatorio ──────────────────────────────────────────────────
    print("=" * 64)
    print("  📊 ANALISE DE ALOCACAO DA CARTEIRA")
    print(f"  Data: {date.today().strftime('%d/%m/%Y')}")
    print(f"  Patrimonio BRL: R$ {total_brl:,.2f}")
    if total_usd:
        print(f"  Patrimonio USD: $ {total_usd:,.2f}")
    print("=" * 64)

    # Tabela atual vs alvo
    print(f"\n{'Classe':<20s} {'% Atual':>8s} {'% Alvo':>8s} {'Diferenca':>10s} {'Status':>12s}")
    print("-" * 64)

    for classe in ["FII", "ACAO", "RENDA_FIXA", "ETF_BR", "ETF_INTL"]:
        alvo = ALOCACAO_ALVO.get(classe, {}).get("alvo", 0)
        custo_atual = atual.get(classe, {}).get("custo", 0)
        pct_atual = (custo_atual / total_brl * 100) if total_brl > 0 else 0
        diff = pct_atual - alvo

        if diff > 10:
            status = "🔴 VENDER"
        elif diff > 3:
            status = "🟡 REDUZIR"
        elif diff < -10:
            status = "🟢 COMPRAR"
        elif diff < -3:
            status = "🟢 AUMENTAR"
        else:
            status = "✅ OK"

        print(f"{classe:<20s} {pct_atual:>7.1f}% {alvo:>7.1f}% {diff:>+9.1f}% {status:>12s}")

    # Problemas de concentracao
    print("\n" + "=" * 64)
    print("  ⚠️  PROBLEMAS DE CONCENTRACAO")
    print("=" * 64)

    cur.execute("""
        SELECT p.ticker, a.tipo, ROUND(p.custo_total::numeric, 2) as custo,
               ROUND((p.custo_total / 
                (SELECT SUM(custo_total) FROM investimentos.posicoes 
                 WHERE ticker NOT IN ('QQQ','SPHD'))) * 100, 1) as pct
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker
        WHERE p.ticker NOT IN ('QQQ','SPHD')
        ORDER BY p.custo_total DESC
    """)
    for ticker, tipo, custo, pct in cur.fetchall():
        if float(pct) > 10:
            print(f"  🔴 {ticker} ({tipo}): {pct}% da carteira — ideal < 10%")

    # Setores FIIs
    cur.execute("""
        SELECT 
            CASE 
                WHEN p.ticker IN ('ALZR11','GARE11','HGLG11') THEN 'Logistica'
                WHEN p.ticker IN ('CPTS11','KNCR11','MXRF11') THEN 'Papel/Recebiveis'
                ELSE 'Hibrido/Outros'
            END as setor,
            ROUND(SUM(p.custo_total)::numeric, 2) as custo,
            ROUND((SUM(p.custo_total) / 
                (SELECT SUM(custo_total) FROM investimentos.posicoes 
                 JOIN investimentos.ativos a2 ON a2.ticker = posicoes.ticker 
                 WHERE a2.tipo = 'FII')) * 100, 1) as pct_fii,
            ROUND((SUM(p.custo_total) / 
                (SELECT SUM(custo_total) FROM investimentos.posicoes 
                 WHERE ticker NOT IN ('QQQ','SPHD'))) * 100, 1) as pct_total
        FROM investimentos.posicoes p
        JOIN investimentos.ativos a ON a.ticker = p.ticker AND a.tipo = 'FII'
        GROUP BY 1
        ORDER BY SUM(p.custo_total) DESC
    """)
    print("\n  Setores FIIs:")
    for setor, custo, pct_fii, pct_total in cur.fetchall():
        bar = '█' * int(float(pct_total) / 3)
        print(f"  {setor:<20s}: {pct_total:>5.1f}% da carteira {bar}")

    # ── Plano de migracao ──────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  🗺️  PLANO DE MIGRACAO (12 meses)")
    print("  Aporte mensal: R$ 1.000")
    print("=" * 64)

    print(f"\n  {'Mes':<6s} {'Acao':<25s} {'Classe':<14s} {'Valor':>10s} {'% Alvo':>8s}")
    print("  " + "-" * 62)

    # Prioridade: classes mais abaixo do alvo primeiro
    deficit = {}
    for classe in ["RENDA_FIXA", "ETF_BR", "ETF_INTL", "ACAO"]:
        alvo = ALOCACAO_ALVO.get(classe, {}).get("alvo", 0)
        custo_atual = atual.get(classe, {}).get("custo", 0)
        pct_atual = (custo_atual / total_brl * 100) if total_brl > 0 else 0
        deficit[classe] = max(0, alvo - pct_atual)

    # Simular 12 meses
    total_futuro = total_brl + 12000
    mes_atual = 1
    for classe in sorted(deficit, key=deficit.get, reverse=True):
        meses_aloc = min(6, max(1, int(deficit[classe] / sum(deficit.values()) * 12)))
        alvo_classe = ALOCACAO_ALVO[classe]["alvo"]
        exemplos = ALOCACAO_ALVO[classe]["exemplos"]
        valor_mensal = 1000 / max(len(deficit), 1)

        print(f"  Meses {mes_atual:>2d}-{mes_atual+meses_aloc-1:<2d} "
              f"{'Comprar ' + classe:<25s} {classe:<14s} "
              f"R$ {valor_mensal * meses_aloc:>8,.0f} {alvo_classe:>7.1f}%")
        print(f"  {'':6s} Ex: {exemplos:<54s}")
        mes_atual += meses_aloc
        if mes_atual > 12:
            break

    # Melhor pratica
    print(f"\n  {'Mes':<6s} {'Acao':<55s}")
    print("  " + "-" * 62)
    print(f"  {'1-6':<6s} {'Prioridade: Renda Fixa + ETFs (zerar deficit de protecao)':<55s}")
    print(f"  {'6-12':<6s} {'Acoes growth/valor: reforcar BBAS3, PETR4, ITSA3, WEGE3':<55s}")
    print(f"  {'12+':<6s} {'FIIs: so comprar se MUITO abaixo do PM e P/VP < 0.85':<55s}")

    print("\n" + "=" * 64)
    print("  📋 REGRAS DE REBALANCEAMENTO")
    print("=" * 64)
    print("""
  1. 🛑 FIIs: NAO comprar mais ate voltar a < 30% da carteira
     - Excecao: se P/VP < 0.80 E abaixo do PM (oportunidade rara)

  2. 🟢 Renda Fixa: todo mes, R$ 300-400 em Tesouro Selic ou CDB 100% CDI
     - Reserva de emergencia = 6 meses de gastos
     - Serve como "municao" para comprar em quedas

  3. 🟢 ETFs: R$ 200-300/mes em BOVA11 ou DIVO11
     - Diversificacao instantanea com 1 ticker

  4. 🟡 Acoes: usar o restante para reforcar posicoes boas
     - Prioridade: P/VP < 1.0 e abaixo do PM
     - BRSR6 (P/VP=0.50), BBAS3 (P/VP=0.63), SAPR3 (P/VP=0.99)

  5. 🌎 Internacional: quando abrir conta global, IVVB11 ou WRLD11
""")

    conn.close()


if __name__ == "__main__":
    main()