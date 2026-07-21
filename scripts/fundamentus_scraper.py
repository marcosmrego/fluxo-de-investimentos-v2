#!/usr/bin/env python3
"""
fundamentus_scraper.py — Coleta indicadores fundamentalistas (P/VP, DY) do Fundamentus
para todos os ativos da carteira e grava em investimentos.indicadores_fundamentalistas.
"""

import re
import time
import urllib.request

import psycopg2
from psycopg2.extras import execute_values

from db_utils import DB_CONFIG

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
TIMEOUT = 15


def fetch_fundamentus(ticker: str) -> dict | None:
    """Extrai P/VP, DY e cotacao do Fundamentus para um ticker."""
    url = f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            html = r.read().decode("latin-1")

        def extract(pattern, html, group=1):
            m = re.search(pattern, html)
            return m.group(group).replace(",", ".") if m else None

        # P/VP
        pvp_str = extract(r'P/VP</span></td>\s*<td[^>]*>\s*<span[^>]*>([\d,.]+)</span>', html)
        if not pvp_str:
            pvp_str = extract(r'P/VP[^<]*</td>\s*<td[^>]*>([\d,.]+)', html)

        # DY
        dy_str = extract(r'Div\. Yield</span></td>\s*<td[^>]*>\s*<span[^>]*>([\d,.]+)%</span>', html)
        if not dy_str:
            dy_str = extract(r'Div\. Yield[^<]*</td>\s*<td[^>]*>([\d,.]+)%', html)

        # Cotacao
        cot_str = extract(r'Cotação</span></td>\s*<td[^>]*>\s*<span[^>]*>([\d,.]+)</span>', html)
        if not cot_str:
            cot_str = extract(r'Cotação[^<]*</td>\s*<td[^>]*>([\d,.]+)', html)

        return {
            "ticker": ticker,
            "pvp": float(pvp_str) if pvp_str else None,
            "dy": float(dy_str) if dy_str else None,
            "cotacao": float(cot_str) if cot_str else None,
        }
    except urllib.error.HTTPError as e:
        print(f"  [{ticker}] HTTP {e.code} — pulando")
        return None
    except Exception as e:
        print(f"  [{ticker}] ERRO: {str(e)[:80]}")
        return None


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        SELECT a.ticker, a.tipo
        FROM investimentos.ativos a
        JOIN investimentos.posicoes p ON p.ticker = a.ticker
        WHERE a.tipo IN ('FII', 'ACAO')
        ORDER BY a.tipo, a.ticker
    """)
    ativos = cur.fetchall()

    print(f"=== Coletando indicadores para {len(ativos)} ativos ===\n")
    data_rows = []
    erros = 0

    for ticker, tipo in ativos:
        print(f"[{ticker}] ({tipo}) ...", end=" ", flush=True)
        d = fetch_fundamentus(ticker)
        if d and d["pvp"] is not None:
            data_rows.append((ticker, d["pvp"], d["dy"], d["cotacao"]))
            print(f"P/VP={d['pvp']:.2f} DY={d['dy']:.1f}%")
        else:
            print("sem dados")
            erros += 1
        time.sleep(0.4)  # Respeitar rate limit

    if data_rows:
        execute_values(
            cur,
            """INSERT INTO investimentos.indicadores_fundamentalistas
               (ticker, pvp, dy_percentual, cotacao)
               VALUES %s
               ON CONFLICT (ticker, data_referencia) DO UPDATE SET
               pvp = EXCLUDED.pvp,
               dy_percentual = EXCLUDED.dy_percentual,
               cotacao = EXCLUDED.cotacao""",
            data_rows,
            page_size=50,
        )
        print(f"\n{len(data_rows)} indicadores gravados. {erros} erros.")
    else:
        print("\nNenhum indicador coletado.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()