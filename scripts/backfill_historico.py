#!/usr/bin/env python3
"""Backfill historico — Yahoo Finance 6 meses para todos os ativos + indices"""
import json, time
import urllib.request
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone

from db_utils import DB_CONFIG as DB

TICKERS_BR = [
    "BBAS3", "BBDC4", "BBSE3", "BEES3", "BRSR6", "CMIG4", "ITSA3", "JHSF3",
    "KLBN3", "PETR4", "POMO4", "SANB3", "SAPR3", "VALE3", "VULC3", "WEGE3",
    "BOVA11", "SPXB11", "LFTB11",
]
FIIS = ["ALZR11", "CPTS11", "GARE11", "HGLG11", "HGRU11", "KNCR11", "KNRI11", "MCHF11", "MXRF11", "VGHF11"]
INDICES = [("^BVSP", "IBOV"), ("IFIX.SA", "IFIX")]
ETFS_INTL = ["QQQ", "SPHD"]

def fetch_ohlcv(symbol, range_d="6mo", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_d}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quotes = result["indicators"]["quote"][0]
        rows = []
        for i, ts in enumerate(timestamps):
            c = quotes["close"][i]
            if c is None:
                continue
            o = quotes["open"][i]
            h = quotes["high"][i]
            l = quotes["low"][i]
            v = quotes["volume"][i] or 0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            rows.append((dt, o, h, l, c, int(v)))
        return rows
    except Exception as e:
        print(f"  ERRO {symbol}: {str(e)[:80]}")
        return []

conn = psycopg2.connect(**DB)
cur = conn.cursor()
total = 0

print("=" * 50)
print("BACKFILL HISTORICO — Yahoo Finance 6mo")
print("=" * 50)

for grupo, tickers, sufixo in [
    ("Acoes/ETFs BR", TICKERS_BR, ".SA"),
    ("FIIs", FIIS, ".SA"),
    ("Indices", ["^BVSP", "IFIX.SA"], ""),
    ("ETFs Intl", ETFS_INTL, ""),
]:
    nomes = {"^BVSP": "IBOV", "IFIX.SA": "IFIX"}
    label = nomes.get(grupo, grupo)
    print(f"\n[{grupo}]")
    for t in tickers:
        symbol = t + (sufixo if sufixo and t not in nomes else "")
        ticker_db = nomes.get(t, t)
        rows = fetch_ohlcv(symbol)
        if rows:
            values = [(ticker_db, d, o, h, l, c, v, 'yfinance') for d, o, h, l, c, v in rows]
            execute_values(cur, """
                INSERT INTO investimentos.cotacoes (ticker, data, abertura, maxima, minima, fechamento, volume, fonte)
                VALUES %s
                ON CONFLICT (ticker, data) DO UPDATE SET
                    abertura=EXCLUDED.abertura, maxima=EXCLUDED.maxima,
                    minima=EXCLUDED.minima, fechamento=EXCLUDED.fechamento,
                    volume=EXCLUDED.volume
            """, values, page_size=500)
            conn.commit()
            total += len(values)
            print(f"  {ticker_db}: {len(values)} dias")
        time.sleep(0.3)

# Rentabilidade diaria historica
print("\n[Rentabilidade Diaria]")
cur.execute("""
    INSERT INTO investimentos.rentabilidade_diaria (data, valor_total, custo_total, lucro_prejuizo, rentabilidade)
    SELECT 
        c.data,
        SUM(c.fechamento * p.quantidade_total),
        SUM(p.custo_total),
        SUM((c.fechamento - p.preco_medio) * p.quantidade_total),
        ROUND((SUM(c.fechamento * p.quantidade_total) / SUM(p.custo_total) - 1) * 100, 4)
    FROM investimentos.cotacoes c
    JOIN investimentos.posicoes p ON p.ticker = c.ticker
    WHERE p.quantidade_total > 0
    GROUP BY c.data
    ON CONFLICT (data) DO UPDATE SET
        valor_total=EXCLUDED.valor_total, custo_total=EXCLUDED.custo_total,
        lucro_prejuizo=EXCLUDED.lucro_prejuizo, rentabilidade=EXCLUDED.rentabilidade
""")
conn.commit()

cur.execute("SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(data), MAX(data) FROM investimentos.cotacoes")
r = cur.fetchone()
cur.execute("SELECT COUNT(*) FROM investimentos.rentabilidade_diaria")
rd = cur.fetchone()[0]
conn.close()

print(f"\n{'='*50}")
print(f"CONCLUIDO! {total} novas insercoes")
print(f"Cotacoes: {r[0]} total | {r[1]} tickers | {r[2]} a {r[3]}")
print(f"Rentabilidade: {rd} registros")
print(f"{'='*50}")