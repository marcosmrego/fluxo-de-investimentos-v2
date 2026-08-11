#!/usr/bin/env python3
"""Atualiza cotações de todos os ativos com posição aberta."""

import json
import argparse
import time
import urllib.request
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

from db_utils import DB_CONFIG
from processar_nota_xp import garantir_cadastros_ativos


PORTFOLIO_SQL = """
    SELECT DISTINCT p.ticker, a.moeda
    FROM investimentos.posicoes p
    JOIN investimentos.ativos a ON a.ticker = p.ticker
    WHERE p.quantidade_total > 0 AND a.monitorar = TRUE
    ORDER BY p.ticker
"""

def yahoo_symbol(ticker: str, moeda: str = "BRL") -> str:
    return ticker if moeda == "USD" else f"{ticker}.SA"


def fetch_chart(symbol: str, range_days: str = "1mo") -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range={range_days}&interval=1d"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def parse_chart(ticker: str, payload: dict) -> list[tuple]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quotes = result["indicators"]["quote"][0]
    rows = []
    previous_close = None
    for index, timestamp in enumerate(timestamps):
        close = quotes["close"][index]
        if close is None:
            continue
        variation = None
        if previous_close not in (None, 0):
            variation = round((close / previous_close - 1) * 100, 4)
        rows.append((
            ticker,
            datetime.fromtimestamp(timestamp, tz=timezone.utc).date(),
            quotes["open"][index],
            quotes["high"][index],
            quotes["low"][index],
            close,
            int(quotes["volume"][index] or 0),
            variation,
            "yahoo",
        ))
        previous_close = close
    return rows


def normalizar_para_brl(
    rows: list[tuple], moeda: str, cambio_por_data: dict
) -> list[tuple]:
    """Converte OHLC para BRL, preservando fechamento e moeda de origem."""
    normalized = []
    previous_close_brl = None
    available_dates = sorted(cambio_por_data)
    for row in rows:
        ticker, quote_date, opening, high, low, close, volume, _, source = row
        rate = 1.0
        if moeda != "BRL":
            eligible = [day for day in available_dates if day <= quote_date]
            if not eligible:
                raise ValueError(f"sem câmbio {moeda}/BRL para {quote_date}")
            rate = cambio_por_data[eligible[-1]]
        converted = tuple(
            round(value * rate, 6) if value is not None else None
            for value in (opening, high, low, close)
        )
        variation = None
        if previous_close_brl not in (None, 0):
            variation = round((converted[3] / previous_close_brl - 1) * 100, 4)
        normalized.append((
            ticker, quote_date, *converted, volume, variation, source,
            moeda, close, rate,
        ))
        previous_close_brl = converted[3]
    return normalized


def atualizar(conn) -> tuple[int, list[str]]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT p.ticker
        FROM investimentos.posicoes p
        LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
        WHERE p.quantidade_total > 0 AND a.ticker IS NULL
        ORDER BY p.ticker
    """)
    orfaos = [row[0] for row in cursor.fetchall()]
    if orfaos:
        garantir_cadastros_ativos(
            conn, [{"ticker": ticker} for ticker in orfaos]
        )
        conn.commit()

    cursor.execute(PORTFOLIO_SQL)
    assets = cursor.fetchall()
    if not assets:
        raise RuntimeError("nenhum ativo monitorado com posição aberta")

    currencies = {currency for _, currency in assets}
    fx_by_currency = {"BRL": {}}
    if "USD" in currencies:
        fx_rows = parse_chart("USDBRL", fetch_chart("BRL=X"))
        fx_by_currency["USD"] = {row[1]: row[5] for row in fx_rows}

    total = 0
    failures = []
    for ticker, currency in assets:
        try:
            native_rows = parse_chart(
                ticker, fetch_chart(yahoo_symbol(ticker, currency))
            )
            rows = normalizar_para_brl(
                native_rows, currency, fx_by_currency[currency]
            )
            if not rows:
                raise RuntimeError("fonte retornou série vazia")
            execute_values(cursor, """
                INSERT INTO investimentos.cotacoes
                    (ticker, data, abertura, maxima, minima, fechamento,
                     volume, variacao_pct, fonte, moeda,
                     fechamento_origem, taxa_cambio)
                VALUES %s
                ON CONFLICT (ticker, data) DO UPDATE SET
                    abertura = EXCLUDED.abertura,
                    maxima = EXCLUDED.maxima,
                    minima = EXCLUDED.minima,
                    fechamento = EXCLUDED.fechamento,
                    volume = EXCLUDED.volume,
                    variacao_pct = EXCLUDED.variacao_pct,
                    fonte = EXCLUDED.fonte,
                    moeda = EXCLUDED.moeda,
                    fechamento_origem = EXCLUDED.fechamento_origem,
                    taxa_cambio = EXCLUDED.taxa_cambio
            """, rows, page_size=100)
            conn.commit()
            total += len(rows)
            print(f"[OK] {ticker}: {len(rows)} pregões")
        except Exception as exc:
            conn.rollback()
            failures.append(ticker)
            print(f"[ERRO] {ticker}: {exc}")
        time.sleep(0.2)

    cursor.close()
    return total, failures


def auditar(conn) -> tuple[int, int, int, object]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(DISTINCT p.ticker),
            COUNT(DISTINCT a.ticker),
            COUNT(DISTINCT c.ticker),
            MAX(c.data)
        FROM investimentos.posicoes p
        LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
        LEFT JOIN investimentos.cotacoes c
          ON c.ticker = p.ticker
         AND c.data >= CURRENT_DATE - INTERVAL '7 days'
        WHERE p.quantidade_total > 0 AND a.monitorar = TRUE
    """)
    result = cursor.fetchone()
    cursor.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        total, failures = (0, []) if args.audit_only else atualizar(conn)
        positions, registered, quoted, latest = auditar(conn)
    finally:
        conn.close()
    if not args.audit_only:
        print(f"Cotações gravadas/atualizadas: {total}")
    print(
        f"Cobertura: posições={positions}, cadastrados={registered}, "
        f"cotados_7d={quoted}, data_mais_recente={latest}"
    )
    if registered != positions or quoted != positions:
        print("Cobertura incompleta da carteira")
        return 1
    if failures:
        print("Tickers sem atualização: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
