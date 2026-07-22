"""SQL queries e funções de acesso ao banco."""

import os
import sys
from pathlib import Path

# Adiciona scripts/ ao path para usar db_utils
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from db_utils import DB_CONFIG
import psycopg2
import psycopg2.extras
import pandas as pd


def _connect():
    """Retorna conexão com o banco."""
    return psycopg2.connect(**DB_CONFIG)


def get_posicoes() -> pd.DataFrame:
    """Posições atuais com cotação do dia."""
    q = """
    SELECT
        p.ticker,
        a.nome,
        a.tipo,
        a.setor,
        p.quantidade_total,
        p.preco_medio,
        p.custo_total,
        c.fechamento AS preco_atual,
        ROUND((c.fechamento - p.preco_medio) * p.quantidade_total, 2) AS lucro_prejuizo,
        ROUND(((c.fechamento - p.preco_medio) / p.preco_medio) * 100, 2) AS rentabilidade_pct,
        ROUND(c.fechamento * p.quantidade_total, 2) AS saldo_atual,
        c.variacao_pct AS var_dia_pct
    FROM investimentos.posicoes p
    LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
    LEFT JOIN LATERAL (
        SELECT fechamento, variacao_pct
        FROM investimentos.cotacoes
        WHERE ticker = p.ticker
        ORDER BY data DESC
        LIMIT 1
    ) c ON true
    ORDER BY saldo_atual DESC NULLS LAST
    """
    with _connect() as conn:
        return pd.read_sql(q, conn)


def get_patrimonio_total() -> dict:
    """Retorna valor total da carteira e custo total."""
    q = """
    SELECT
        COALESCE(SUM(c.fechamento * p.quantidade_total), 0) AS valor_atual,
        COALESCE(SUM(p.custo_total), 0) AS custo_total
    FROM investimentos.posicoes p
    LEFT JOIN LATERAL (
        SELECT fechamento
        FROM investimentos.cotacoes
        WHERE ticker = p.ticker
        ORDER BY data DESC
        LIMIT 1
    ) c ON true
    """
    with _connect() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(q)
        row = cur.fetchone()
        return dict(row) if row else {"valor_atual": 0, "custo_total": 0}


def get_rentabilidade_historica(dias: int = 90) -> pd.DataFrame:
    """Histórico de rentabilidade diária."""
    q = """
    SELECT data, valor_total, custo_total, lucro_prejuizo, rentabilidade
    FROM investimentos.rentabilidade_diaria
    ORDER BY data DESC
    LIMIT %s
    """
    with _connect() as conn:
        df = pd.read_sql(q, conn, params=(dias,))
        df = df.sort_values("data")
        return df


def get_proventos(meses: int = 12) -> pd.DataFrame:
    """Proventos dos últimos N meses."""
    q = """
    SELECT ticker, data_pgto, valor, tipo
    FROM investimentos.proventos
    WHERE data_pgto >= NOW() - INTERVAL '%s months'
    ORDER BY data_pgto DESC
    """
    with _connect() as conn:
        return pd.read_sql(q, conn, params=(meses,))


def get_proventos_agregado() -> dict:
    """Totais de proventos."""
    q = """
    SELECT
        COALESCE(SUM(CASE WHEN data_pgto >= DATE_TRUNC('year', NOW()) THEN valor END), 0) AS ano_atual,
        COALESCE(SUM(CASE WHEN data_pgto >= DATE_TRUNC('month', NOW()) THEN valor END), 0) AS mes_atual,
        COALESCE(SUM(CASE WHEN data_pgto >= NOW() - INTERVAL '12 months' THEN valor END), 0) AS doze_meses
    FROM investimentos.proventos
    """
    with _connect() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(q)
        return dict(cur.fetchone())


def get_indicadores() -> pd.DataFrame:
    """Indicadores fundamentalistas (versão mais completa)."""
    q = """
    SELECT
        ticker,
        p_l, p_vp, roe, roic,
        marg_liquida, marg_bruta,
        dividend_yield,
        cres_rec_5a,
        div_liq_patrim,
        osc_12m,
        data_coleta
    FROM investimentos.indicadores_fundamentalistas_v2
    WHERE (ticker, data_coleta) IN (
        SELECT ticker, MAX(data_coleta)
        FROM investimentos.indicadores_fundamentalistas_v2
        GROUP BY ticker
    )
    ORDER BY ticker
    """
    with _connect() as conn:
        return pd.read_sql(q, conn)


def get_distribuicao_tipo() -> pd.DataFrame:
    """Distribuição da carteira por tipo de ativo."""
    q = """
    SELECT
        COALESCE(a.tipo, 'Outros') AS tipo,
        ROUND(SUM(c.fechamento * p.quantidade_total), 2) AS valor
    FROM investimentos.posicoes p
    LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
    LEFT JOIN LATERAL (
        SELECT fechamento
        FROM investimentos.cotacoes
        WHERE ticker = p.ticker
        ORDER BY data DESC
        LIMIT 1
    ) c ON true
    GROUP BY a.tipo
    ORDER BY valor DESC
    """
    with _connect() as conn:
        return pd.read_sql(q, conn)