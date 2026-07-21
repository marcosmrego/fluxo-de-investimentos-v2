#!/usr/bin/env python3
"""
coletar_proventos.py — Coleta historico de dividendos/proventos via Yahoo Finance
e grava na tabela investimentos.proventos.

Fonte: Yahoo Finance v8/chart com events=div
- FIIs: pagamentos mensais com data consistente
- Ações: dividendos + JCP trimestrais/semestrais
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta

import psycopg2
from psycopg2.extras import execute_values

# ── Config ──────────────────────────────────────────────────────────────
from db_utils import DB_CONFIG

YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 15  # segundos

# ── Helpers ─────────────────────────────────────────────────────────────

def business_days_before(dt: date, days: int) -> date:
    """Retorna 'days' dias uteis antes de dt (aproximacao: pula sab/dom)."""
    result = dt
    skipped = 0
    while skipped < days:
        result = result - timedelta(days=1)
        if result.weekday() < 5:  # seg-sex
            skipped += 1
    return result


def fetch_dividends(ticker: str) -> list[dict]:
    """Busca dividendos historicos de um ticker via Yahoo Finance."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?"
        f"range=2y&interval=3mo&events=div"
    )
    try:
        req = urllib.request.Request(url, headers=YAHOO_HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        divs = result.get("events", {}).get("dividends", {})
        meta = result["meta"]

        rows = []
        for ts_str, d in sorted(divs.items()):
            dt = datetime.fromtimestamp(d["date"]).date()
            rows.append({
                "ticker": ticker.replace(".SA", ""),
                "data_pgto": dt,
                "valor": float(d["amount"]),
                "preco_atual": meta.get("regularMarketPrice"),
            })
        return rows
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  [skip] {ticker}: 404 — nao encontrado na API Yahoo")
        else:
            print(f"  [erro] {ticker}: HTTP {e.code}")
        return []
    except Exception as e:
        print(f"  [erro] {ticker}: {str(e)[:80]}")
        return []


def classify_type(ticker: str) -> str:
    """Classifica o tipo de provento baseado no ticker."""
    if ticker.endswith("11"):
        return "RENDIMENTO"  # FII
    return "DIVIDENDO"


def estimate_data_com(pgto_date: date, ticker: str) -> date:
    """Estima a data-com (ultimo dia para comprar com direito ao provento)."""
    if ticker.endswith("11"):
        # FIIs: data-com ~5 dias uteis antes do pagamento
        return business_days_before(pgto_date, 5)
    else:
        # Acoes: data-com ~10 dias uteis antes (dividendos + JCP)
        return business_days_before(pgto_date, 10)


# ── Main ────────────────────────────────────────────────────────────────

def main():
    # Conectar banco
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # Pegar todos os tickers da carteira
    cur.execute("SELECT ticker, tipo FROM investimentos.ativos ORDER BY tipo, ticker")
    ativos = cur.fetchall()

    print(f"=== Coletando proventos para {len(ativos)} ativos ===\n")

    total_inserts = 0
    total_erros = 0

    for ticker, tipo in ativos:
        # Yahoo Finance espera sufixo .SA
        symbol = f"{ticker}.SA"
        print(f"[{ticker}] ({tipo}) buscando...", end=" ", flush=True)

        dividendos = fetch_dividends(symbol)
        if not dividendos:
            total_erros += 1
            print("sem dados")
            continue

        # Enriquecer e preparar inserts
        inserts = []
        for d in dividendos:
            data_com = estimate_data_com(d["data_pgto"], ticker)
            inserts.append((
                ticker,
                d["data_pgto"],
                data_com,
                d["valor"],
                classify_type(ticker),
                "yahoo",
            ))

        # Upsert em lote
        execute_values(
            cur,
            """INSERT INTO investimentos.proventos
               (ticker, data_pgto, data_com_estimada, valor, tipo, fonte)
               VALUES %s
               ON CONFLICT (ticker, data_pgto, valor) DO NOTHING""",
            inserts,
            page_size=100,
        )

        print(f"{len(inserts)} proventos (preco: R$ {dividendos[0].get('preco_atual','?')})")
        total_inserts += len(inserts)

        # Respeitar rate limit
        time.sleep(0.3)

    cur.close()
    conn.close()

    print(f"\n=== Resumo ===")
    print(f"Ativos processados: {len(ativos)}")
    print(f"Proventos coletados: {total_inserts}")
    print(f"Erros/sem dados: {total_erros}")


if __name__ == "__main__":
    main()