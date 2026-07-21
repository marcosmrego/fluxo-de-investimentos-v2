#!/usr/bin/env python3
"""
fundamentus_scraper_v2.py — Coleta TODOS os indicadores fundamentalistas do Fundamentus
para ações e FIIs da carteira. Grava em investimentos.indicadores_fundamentalistas_v2.

Indicadores Ações (22): P/L, LPA, P/VP, VPA, P/EBIT, Marg.Bruta, PSR, Marg.EBIT,
  P/Ativos, Marg.Líquida, P/Cap.Giro, EBIT/Ativo, P/Ativ Circ Liq, ROIC, Div.Yield,
  ROE, EV/EBITDA, Liquidez Corr, EV/EBIT, Dív Líq/Patrim, Cres.Rec(5a), Giro Ativos

Indicadores FIIs (16): FFO Yield, FFO/Cota, Div.Yield, Dividendo/Cota, P/VP, VP/Cota,
  Receita 12m/3m, Venda Ativos 12m/3m, FFO 12m/3m, Rend.Distrib. 12m/3m,
  Ativos Total, Patrim.Líquido

Oscilações (ambos): dia, mês, 30d, 12m, ano atual
"""

import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date

import psycopg2
from psycopg2.extras import execute_values

# ── Config ──────────────────────────────────────────────────────────────
from db_utils import DB_CONFIG

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 20
SLEEP_BETWEEN = 0.5  # segundos entre requisições


# ── Parsing ─────────────────────────────────────────────────────────────

def parse_num(val: str) -> float | None:
    """Converte string brasileira para float. Retorna None se inválido."""
    if not val or val.strip() in ('', '-', '—'):
        return None
    val = val.strip().replace('.', '').replace(',', '.').replace('%', '')
    try:
        return float(val)
    except ValueError:
        return None


def fetch_fundamentus(ticker: str) -> dict | None:
    """Busca e parseia a página do Fundamentus para um ticker."""
    url = f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            html = r.read().decode("latin-1")
    except urllib.error.HTTPError as e:
        print(f"  [{ticker}] HTTP {e.code} — pulando")
        return None
    except Exception as e:
        print(f"  [{ticker}] ERRO: {str(e)[:80]}")
        return None

    # Detectar se é FII ou Ação pela presença de "FFO Yield"
    is_fii = 'FFO Yield' in html or 'FFO/Cota' in html

    if is_fii:
        return _parse_fii(html, ticker)
    else:
        return _parse_acao(html, ticker)


def _parse_acao(html: str, ticker: str) -> dict:
    """Parse indicadores de Ação do Fundamentus."""
    tables = re.findall(r'(<table[^>]*w728[^>]*>.*?</table>)', html, re.DOTALL)

    if len(tables) < 3:
        print(f"  [{ticker}] Não encontrou tabela de indicadores")
        return None

    # Extrair células da 3ª tabela w728 (índice 2)
    cells = re.findall(r'<td[^>]*>(.*?)</td>', tables[2], re.DOTALL)
    texts = []
    for cell in cells:
        text = re.sub(r'<[^>]+>', ' ', cell).strip()
        text = re.sub(r'\s+', ' ', text).strip()
        texts.append(text)

    # Construir mapa label→posição
    label_map = {}
    for i, t in enumerate(texts):
        # Labels conhecidos
        clean = t.replace('?', '').strip()
        if clean in ('P/L', 'LPA', 'P/VP', 'VPA', 'P/EBIT', 'Marg. Bruta',
                      'PSR', 'Marg. EBIT', 'P/Ativos', 'Marg. Líquida',
                      'P/Cap. Giro', 'EBIT / Ativo', 'P/Ativ Circ Liq', 'ROIC',
                      'Div. Yield', 'ROE', 'EV / EBITDA', 'Liquidez Corr',
                      'EV / EBIT', 'Dív Líq / Patrim', 'Cres. Rec (5a)',
                      'Giro Ativos'):
            label_map[clean] = i + 1  # valor está na célula seguinte

    # Oscilações
    osc_map = {}
    for i, t in enumerate(texts):
        if t in ('Dia', 'Mês', '30 dias', '12 meses'):
            osc_map[t] = texts[i + 1] if i + 1 < len(texts) else None

    # Extrair valores
    def val(label):
        idx = label_map.get(label)
        if idx is not None and idx < len(texts):
            return parse_num(texts[idx])
        return None

    # Extrair ano atual (primeira linha de "2026" na tabela)
    ano_atual = str(date.today().year)
    ano_val = None
    for i, t in enumerate(texts):
        if t == ano_atual and i + 1 < len(texts):
            ano_val = parse_num(texts[i + 1])
            break

    resultado = {
        "ticker": ticker,
        "tipo": "ACAO",
        "p_l": val('P/L'),
        "lpa": val('LPA'),
        "p_vp": val('P/VP'),
        "vpa": val('VPA'),
        "p_ebit": val('P/EBIT'),
        "marg_bruta": val('Marg. Bruta'),
        "psr": val('PSR'),
        "marg_ebit": val('Marg. EBIT'),
        "p_ativos": val('P/Ativos'),
        "marg_liquida": val('Marg. Líquida'),
        "p_cap_giro": val('P/Cap. Giro'),
        "ebit_ativo": val('EBIT / Ativo'),
        "p_ativ_circ_liq": val('P/Ativ Circ Liq'),
        "roic": val('ROIC'),
        "dividend_yield": val('Div. Yield'),
        "roe": val('ROE'),
        "ev_ebitda": val('EV / EBITDA'),
        "liquidez_corr": val('Liquidez Corr'),
        "ev_ebit": val('EV / EBIT'),
        "div_liq_patrim": val('Dív Líq / Patrim'),
        "cres_rec_5a": val('Cres. Rec (5a)'),
        "giro_ativos": val('Giro Ativos'),
        "osc_dia": parse_num(osc_map.get('Dia')),
        "osc_mes": parse_num(osc_map.get('Mês')),
        "osc_30d": parse_num(osc_map.get('30 dias')),
        "osc_12m": parse_num(osc_map.get('12 meses')),
        "osc_ano_atual": ano_val,
    }
    return resultado


def _parse_fii(html: str, ticker: str) -> dict:
    """Parse indicadores de FII do Fundamentus."""
    tables = re.findall(r'(<table[^>]*w728[^>]*>.*?</table>)', html, re.DOTALL)

    if len(tables) < 3:
        print(f"  [{ticker}] Não encontrou tabela de indicadores")
        return None

    cells = re.findall(r'<td[^>]*>(.*?)</td>', tables[2], re.DOTALL)
    texts = []
    for cell in cells:
        text = re.sub(r'<[^>]+>', ' ', cell).strip()
        text = re.sub(r'\s+', ' ', text).strip()
        texts.append(text)

    # Mapa label→posição para FIIs
    label_map = {}
    for i, t in enumerate(texts):
        clean = t.replace('?', '').strip()
        if clean in ('FFO Yield', 'FFO/Cota', 'Div. Yield', 'Dividendo/cota',
                      'P/VP', 'VP/Cota', 'Receita', 'Venda de ativos',
                      'FFO', 'Rend. Distribuído', 'Ativos', 'Patrim Líquido'):
            label_map[clean] = i + 1

    # Oscilações
    osc_map = {}
    for i, t in enumerate(texts):
        if t in ('Dia', 'Mês', '30 dias', '12 meses'):
            osc_map[t] = texts[i + 1] if i + 1 < len(texts) else None

    def val(label):
        idx = label_map.get(label)
        if idx is not None and idx < len(texts):
            return parse_num(texts[idx])
        return None

    # Para FIIs, Receita, Venda, FFO, Rend)Distribuído aparecem 2x (12m e 3m)
    # Precisamos pegar por posição. Vamos extrair todas as ocorrências
    def val_nth(label, n=0):
        """Pega a n-ésima ocorrência do label."""
        indices = [i + 1 for i, t in enumerate(texts)
                   if t.replace('?', '').strip() == label]
        if len(indices) > n and indices[n] < len(texts):
            return parse_num(texts[indices[n]])
        return None

    ano_atual = str(date.today().year)
    ano_val = None
    for i, t in enumerate(texts):
        if t == ano_atual and i + 1 < len(texts):
            ano_val = parse_num(texts[i + 1])
            break

    resultado = {
        "ticker": ticker,
        "tipo": "FII",
        "ffo_yield": val('FFO Yield'),
        "ffo_cota": val('FFO/Cota'),
        "dividend_yield": val('Div. Yield'),
        "dividendo_cota": val('Dividendo/cota'),
        "p_vp": val('P/VP'),
        "vp_cota": val('VP/Cota'),
        "receita_12m": val_nth('Receita', 0),
        "receita_3m": val_nth('Receita', 1),
        "venda_ativos_12m": val_nth('Venda de ativos', 0),
        "venda_ativos_3m": val_nth('Venda de ativos', 1),
        "ffo_12m": val_nth('FFO', 0),
        "ffo_3m": val_nth('FFO', 1),
        "rend_distribuido_12m": val_nth('Rend. Distribuído', 0),
        "rend_distribuido_3m": val_nth('Rend. Distribuído', 1),
        "ativos_total": val('Ativos'),
        "patrimonio_liquido": val('Patrim Líquido'),
        "osc_dia": parse_num(osc_map.get('Dia')),
        "osc_mes": parse_num(osc_map.get('Mês')),
        "osc_30d": parse_num(osc_map.get('30 dias')),
        "osc_12m": parse_num(osc_map.get('12 meses')),
        "osc_ano_atual": ano_val,
    }
    return resultado


# ── Inserção no banco ───────────────────────────────────────────────────

COLUNAS_INSERT = [
    "ticker", "data_coleta", "tipo",
    "p_l", "lpa", "p_vp", "vpa", "p_ebit", "marg_bruta", "psr",
    "marg_ebit", "p_ativos", "marg_liquida", "p_cap_giro", "ebit_ativo",
    "p_ativ_circ_liq", "roic", "dividend_yield", "roe", "ev_ebitda",
    "liquidez_corr", "ev_ebit", "div_liq_patrim", "cres_rec_5a",
    "giro_ativos", "osc_dia", "osc_mes", "osc_30d", "osc_12m",
    "osc_ano_atual", "ffo_yield", "ffo_cota", "vp_cota", "dividendo_cota",
    "receita_12m", "receita_3m", "venda_ativos_12m", "venda_ativos_3m",
    "ffo_12m", "ffo_3m", "rend_distribuido_12m", "rend_distribuido_3m",
    "ativos_total", "patrimonio_liquido",
]


def insert_into_db(rows: list[dict]):
    """Insere os indicadores no banco via upsert."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    hoje = date.today()
    data_rows = []
    for r in rows:
        row = [r.get(col) for col in COLUNAS_INSERT]
        # Garantir data_coleta
        row[1] = hoje
        data_rows.append(tuple(row))

    col_placeholders = ", ".join(COLUNAS_INSERT)
    set_clause = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in COLUNAS_INSERT if c not in ("ticker", "data_coleta")
    )

    sql = f"""
        INSERT INTO investimentos.indicadores_fundamentalistas_v2
        ({col_placeholders})
        VALUES %s
        ON CONFLICT (ticker, data_coleta) DO UPDATE SET
        {set_clause}
    """

    execute_values(cur, sql, data_rows, page_size=50)
    print(f"\n{len(data_rows)} indicadores gravados/atualizados no banco.")
    cur.close()
    conn.close()


# ── Main ────────────────────────────────────────────────────────────────

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    # Buscar ativos da carteira (ações + FIIs com posição)
    cur.execute("""
        SELECT a.ticker, a.tipo
        FROM investimentos.ativos a
        JOIN investimentos.posicoes p ON p.ticker = a.ticker
        WHERE a.tipo IN ('ACAO', 'FII') AND p.quantidade_total > 0
        ORDER BY a.tipo, a.ticker
    """)
    ativos = cur.fetchall()
    cur.close()
    conn.close()

    print(f"=== Fundamentus Scraper V2 ===\n"
          f"Data: {date.today()}\n"
          f"Ativos a processar: {len(ativos)}\n")

    resultados = []
    erros = 0

    for ticker, tipo in ativos:
        print(f"[{ticker}] ({tipo}) ...", end=" ", flush=True)
        d = fetch_fundamentus(ticker)
        if d:
            # Contar quantos indicadores vieram preenchidos
            preenchidos = sum(1 for k, v in d.items()
                              if k not in ("ticker", "tipo") and v is not None)
            resultados.append(d)
            print(f"OK — {preenchidos} indicadores")
        else:
            print("FALHA")
            erros += 1

        time.sleep(SLEEP_BETWEEN)

    if resultados:
        insert_into_db(resultados)

    print(f"\n=== Resumo ===")
    print(f"Sucesso: {len(resultados)} ativos")
    print(f"Erros: {erros} ativos")

    # Estatísticas rápidas
    acoes = [r for r in resultados if r.get("tipo") == "ACAO"]
    fiis = [r for r in resultados if r.get("tipo") == "FII"]
    print(f"Ações processadas: {len(acoes)}")
    print(f"FIIs processados: {len(fiis)}")


if __name__ == "__main__":
    main()