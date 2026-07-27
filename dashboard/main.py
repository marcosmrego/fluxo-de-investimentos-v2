"""FastAPI — Dashboard Carteira Prof. Marcos (climate-style)."""

import os
from pathlib import Path
from datetime import date, timedelta

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text

# ── DB Config ──────────────────────────────────────────────────
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

_password = os.environ.get("DB_PASSWORD", "")
if not _password:
    _vault_pg = Path("/opt/data/vault/credentials/postgres.env")
    if _vault_pg.exists():
        for line in _vault_pg.read_text().split("\n"):
            if line.startswith("DB_PASSWORD="):
                _password = line.split("=", 1)[1].strip()
                break

DB_URL = (
    f"postgresql://{os.environ.get('DB_USER', 'postgres')}:{_password}"
    f"@{os.environ.get('DB_HOST', '212.85.22.227')}:"
    f"{os.environ.get('DB_PORT', '5432')}/"
    f"{os.environ.get('DB_NAME', 'carteira_investimentos')}"
)

engine = create_engine(DB_URL)

# ── App ────────────────────────────────────────────────────────
app = FastAPI(title="Dashboard Carteira")

static = Path(__file__).parent / "static"
static.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static)), name="static")


@app.get("/")
async def index():
    return FileResponse(static / "index.html")


# ── Helpers ────────────────────────────────────────────────────
def _df(rows, keys):
    """Converte lista de tuples em lista de dicts."""
    return [dict(zip(keys, r)) for r in rows]


def _one(rows, keys):
    """Retorna primeiro resultado ou None."""
    arr = _df(rows, keys)
    return arr[0] if arr else None


# ── Endpoints ──────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    """KPIs principais: patrimonio, lucro, TWR, proventos."""
    with engine.connect() as conn:
        # Patrimonio
        pat = _one(conn.execute(text("""
            SELECT
                COALESCE(SUM(c.fechamento * p.quantidade_total), 0) AS valor_atual,
                COALESCE(SUM(p.custo_total), 0) AS custo_total
            FROM investimentos.posicoes p
            LEFT JOIN LATERAL (
                SELECT fechamento FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
        """)).fetchall(),
            ["valor_atual", "custo_total"])

        # Proventos
        prov = _one(conn.execute(text("""
            SELECT
                COALESCE(SUM(CASE WHEN data_pgto >= DATE_TRUNC('year', NOW()) THEN valor END), 0) AS ano,
                COALESCE(SUM(CASE WHEN data_pgto >= DATE_TRUNC('month', NOW()) THEN valor END), 0) AS mes
            FROM investimentos.proventos
        """)).fetchall(),
            ["ano", "mes"])

        # Rentabilidade historica (90 dias)
        rent = _df(conn.execute(text("""
            SELECT data, valor_total, custo_total, rentabilidade
            FROM investimentos.rentabilidade_diaria
            ORDER BY data DESC LIMIT 90
        """)).fetchall(),
            ["data", "valor_total", "custo_total", "rentabilidade"])

    val = pat["valor_atual"] or 0
    custo = pat["custo_total"] or 0
    lucro = val - custo
    rent_pct = (lucro / custo * 100) if custo > 0 else 0

    # TWR
    twr_val = 0.0
    if rent:
        returns = [r["rentabilidade"] / 100 for r in rent if r["rentabilidade"] is not None]
        if returns:
            twr_val = round((float(np.prod([1 + r for r in returns])) - 1) * 100, 2)

    return {
        "patrimonio": round(val, 2),
        "custo_total": round(custo, 2),
        "lucro": round(lucro, 2),
        "rentabilidade_pct": round(rent_pct, 2),
        "twr_90d": twr_val,
        "proventos_ano": round(prov["ano"] or 0, 2),
        "proventos_mes": round(prov["mes"] or 0, 2),
    }


@app.get("/api/posicoes")
async def posicoes(
    tipo: str | None = Query(None),
    setor: str | None = Query(None),
):
    """Tabela de posicoes com filtros opcionais."""
    with engine.connect() as conn:
        rows = _df(conn.execute(text("""
            SELECT
                p.ticker, a.nome, a.tipo, a.setor,
                p.quantidade_total, p.preco_medio, p.custo_total,
                c.fechamento AS preco_atual,
                ROUND((c.fechamento - p.preco_medio) * p.quantidade_total, 2) AS lucro_prejuizo,
                ROUND(((c.fechamento - p.preco_medio) / p.preco_medio) * 100, 2) AS rentabilidade_pct,
                ROUND(c.fechamento * p.quantidade_total, 2) AS saldo_atual,
                c.variacao_pct AS var_dia_pct
            FROM investimentos.posicoes p
            LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
            LEFT JOIN LATERAL (
                SELECT fechamento, variacao_pct FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
            ORDER BY saldo_atual DESC NULLS LAST
        """)).fetchall(),
            ["ticker", "nome", "tipo", "setor",
             "quantidade_total", "preco_medio", "custo_total",
             "preco_atual", "lucro_prejuizo", "rentabilidade_pct",
             "saldo_atual", "var_dia_pct"])

    # Filtros
    if tipo and tipo != "Todos":
        rows = [r for r in rows if r["tipo"] == tipo]
    if setor and setor != "Todos":
        rows = [r for r in rows if r["setor"] == setor]

    # Calcular % carteira
    total = sum(r["saldo_atual"] or 0 for r in rows)
    for r in rows:
        r["pct_carteira"] = round((r["saldo_atual"] or 0) / total * 100, 2) if total > 0 else 0

    return {"posicoes": rows, "total_saldo": round(total, 2)}


@app.get("/api/filtros")
async def filtros():
    """Tipos e setores disponíveis para os dropdowns."""
    with engine.connect() as conn:
        tipos = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT a.tipo FROM investimentos.posicoes p LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker WHERE a.tipo IS NOT NULL ORDER BY a.tipo"
        )).fetchall()]
        setores = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT a.setor FROM investimentos.posicoes p LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker WHERE a.setor IS NOT NULL ORDER BY a.setor"
        )).fetchall()]
    return {"tipos": tipos, "setores": setores}


@app.get("/api/distribuicao")
async def distribuicao():
    """Pie chart: distribuição por tipo de ativo."""
    with engine.connect() as conn:
        rows = _df(conn.execute(text("""
            SELECT
                COALESCE(a.tipo, 'Outros') AS tipo,
                ROUND(SUM(c.fechamento * p.quantidade_total), 2) AS valor
            FROM investimentos.posicoes p
            LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
            LEFT JOIN LATERAL (
                SELECT fechamento FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
            GROUP BY a.tipo ORDER BY valor DESC
        """)).fetchall(),
            ["tipo", "valor"])
    return {"distribuicao": rows}


@app.get("/api/rentabilidade")
async def rentabilidade(dias: int = Query(90, ge=30, le=365)):
    """Histórico de rentabilidade + TWR."""
    with engine.connect() as conn:
        rows = _df(conn.execute(text("""
            SELECT data, valor_total, custo_total, lucro_prejuizo, rentabilidade
            FROM investimentos.rentabilidade_diaria
            ORDER BY data DESC LIMIT :dias
        """), {"dias": dias}).fetchall(),
            ["data", "valor_total", "custo_total", "lucro_prejuizo", "rentabilidade"])

    # Ordenar cronologicamente
    rows.sort(key=lambda r: str(r["data"]))

    # TWR
    returns = [r["rentabilidade"] / 100 for r in rows if r["rentabilidade"] is not None]
    twr_val = round((float(np.prod([1 + r for r in returns])) - 1) * 100, 2) if returns else 0

    # Serializar datas
    serialized = []
    for r in rows:
        d = r["data"]
        serialized.append({
            "data": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "valor_total": float(r["valor_total"] or 0),
            "custo_total": float(r["custo_total"] or 0),
            "lucro_prejuizo": float(r["lucro_prejuizo"] or 0),
            "rentabilidade": float(r["rentabilidade"]) if r["rentabilidade"] is not None else 0,
        })

    return {"historico": serialized, "twr": twr_val}


@app.get("/api/proventos")
async def proventos(meses: int = Query(12, ge=1, le=24)):
    """Histórico de proventos."""
    with engine.connect() as conn:
        rows = _df(conn.execute(text("""
            SELECT ticker, data_pgto, valor, tipo
            FROM investimentos.proventos
            WHERE data_pgto >= NOW() - (:meses || ' months')::INTERVAL
            ORDER BY data_pgto DESC
        """), {"meses": str(meses)}).fetchall(),
            ["ticker", "data_pgto", "valor", "tipo"])

    serialized = []
    for r in rows:
        d = r["data_pgto"]
        serialized.append({
            "ticker": r["ticker"],
            "data_pgto": d.isoformat() if hasattr(d, "isoformat") else str(d),
            "valor": float(r["valor"] or 0),
            "tipo": r["tipo"],
        })

    # Totais
    ano = sum(r["valor"] for r in serialized if r["data_pgto"] >= str(date.today().year))
    mes_atual = sum(r["valor"] for r in serialized if r["data_pgto"][:7] == date.today().strftime("%Y-%m"))

    return {
        "proventos": serialized,
        "total_ano": round(ano, 2),
        "total_mes": round(mes_atual, 2),
    }


@app.get("/api/indicadores")
async def indicadores():
    """Indicadores fundamentalistas + Bazin/Graham."""
    with engine.connect() as conn:
        rows = _df(conn.execute(text("""
            SELECT ticker, p_l, p_vp, roe, roic,
                   marg_liquida, marg_bruta, dividend_yield,
                   cres_rec_5a, div_liq_patrim, osc_12m, data_coleta
            FROM investimentos.indicadores_fundamentalistas_v2
            WHERE (ticker, data_coleta) IN (
                SELECT ticker, MAX(data_coleta)
                FROM investimentos.indicadores_fundamentalistas_v2
                GROUP BY ticker
            )
            ORDER BY ticker
        """)).fetchall(),
            ["ticker", "p_l", "p_vp", "roe", "roic",
             "marg_liquida", "marg_bruta", "dividend_yield",
             "cres_rec_5a", "div_liq_patrim", "osc_12m", "data_coleta"])

    serialized = []
    for r in rows:
        item = {
            "ticker": r["ticker"],
            "p_l": float(r["p_l"]) if r["p_l"] else None,
            "p_vp": float(r["p_vp"]) if r["p_vp"] else None,
            "roe": float(r["roe"]) if r["roe"] else None,
            "roic": float(r["roic"]) if r["roic"] else None,
            "marg_liquida": float(r["marg_liquida"]) if r["marg_liquida"] else None,
            "marg_bruta": float(r["marg_bruta"]) if r["marg_bruta"] else None,
            "dividend_yield": float(r["dividend_yield"]) if r["dividend_yield"] else None,
            "cres_rec_5a": float(r["cres_rec_5a"]) if r["cres_rec_5a"] else None,
            "div_liq_patrim": float(r["div_liq_patrim"]) if r["div_liq_patrim"] else None,
            "osc_12m": float(r["osc_12m"]) if r["osc_12m"] else None,
        }

        # Bazin
        dy = float(r["dividend_yield"] or 0)
        item["bazin"] = round(dy / 6, 2) if dy > 0 else 0

        # Graham
        lpa = float(r["p_l"] or 0)
        vpa = float(r["p_vp"] or 0)
        lpa_val = (100 / lpa) if lpa > 0 else 0
        vpa_val = (100 / vpa) if vpa > 0 else 0
        item["graham"] = round(float(np.sqrt(22.5 * lpa_val * vpa_val)), 2) if (lpa_val > 0 and vpa_val > 0) else 0

        serialized.append(item)

    ultima_coleta = max(
        (r["data_coleta"] for r in rows if r["data_coleta"]),
        default=None
    )

    return {
        "indicadores": serialized,
        "data_coleta": ultima_coleta.isoformat() if hasattr(ultima_coleta, "isoformat") else str(ultima_coleta) if ultima_coleta else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}