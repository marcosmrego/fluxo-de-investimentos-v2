"""FastAPI — Dashboard Carteira Prof. Marcos (climate-style)."""

import os
import base64
import binascii
import secrets
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import URL, create_engine, text

from dashboard.metrics import percentage_change, portfolio_weight

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

DB_URL = URL.create(
    "postgresql+psycopg2",
    username=os.environ.get("DB_USER", "postgres"),
    password=_password,
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", "5432")),
    database=os.environ.get("DB_NAME", "carteira_investimentos"),
)

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=300)

_dashboard_username = os.environ.get("DASHBOARD_USERNAME", "")
_dashboard_password = os.environ.get("DASHBOARD_PASSWORD", "")
if not _dashboard_username:
    raise RuntimeError("DASHBOARD_USERNAME must be configured")
if not _dashboard_password:
    raise RuntimeError("DASHBOARD_PASSWORD must be configured")

# ── App ────────────────────────────────────────────────────────
app = FastAPI(title="Dashboard Carteira", docs_url=None, redoc_url=None)


def _authenticated(authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
        username, password = raw.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    return secrets.compare_digest(username, _dashboard_username) and secrets.compare_digest(
        password, _dashboard_password
    )


@app.middleware("http")
async def protect_dashboard(request: Request, call_next):
    if request.url.path != "/health" and not _authenticated(
        request.headers.get("authorization")
    ):
        return JSONResponse(
            {"detail": "authentication required"},
            status_code=401,
            headers={"WWW-Authenticate": "Basic"},
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response

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
                COALESCE(SUM(p.custo_total) FILTER (WHERE c.fechamento IS NOT NULL), 0) AS custo_coberto,
                COALESCE(SUM(p.custo_total), 0) AS custo_total,
                COUNT(*) FILTER (WHERE c.fechamento IS NULL) AS posicoes_sem_cotacao
            FROM investimentos.posicoes p
            LEFT JOIN LATERAL (
                SELECT fechamento FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
        """)).fetchall(),
            ["valor_atual", "custo_coberto", "custo_total", "posicoes_sem_cotacao"])

    val = pat["valor_atual"] or 0
    custo_coberto = pat["custo_coberto"] or 0
    cobertura_completa = pat["posicoes_sem_cotacao"] == 0
    lucro = val - custo_coberto if cobertura_completa else None
    rent_pct = (lucro / custo_coberto * 100) if lucro is not None and custo_coberto > 0 else None

    return {
        "patrimonio_coberto": round(val, 2),
        "patrimonio": round(val, 2) if cobertura_completa else None,
        "custo_total": round(pat["custo_total"] or 0, 2),
        "lucro": round(lucro, 2) if lucro is not None else None,
        "rentabilidade_pct": round(rent_pct, 2) if rent_pct is not None else None,
        "cobertura_completa": cobertura_completa,
        "posicoes_sem_cotacao": pat["posicoes_sem_cotacao"],
        "twr_90d": None,
        "twr_status": "indisponivel_sem_fluxos_de_caixa",
        "proventos_ano": None,
        "proventos_mes": None,
        "proventos_status": "indisponiveis_sem_quantidade_na_data_com",
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
                c.variacao_pct AS var_dia_pct,
                c.data AS data_cotacao,
                p.atualizado_em,
                (a.ticker IS NOT NULL) AS cadastrado,
                (c.fechamento IS NOT NULL) AS possui_cotacao
            FROM investimentos.posicoes p
            LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
            LEFT JOIN LATERAL (
                SELECT fechamento, variacao_pct, data FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
            ORDER BY saldo_atual DESC NULLS LAST
        """)).fetchall(),
            ["ticker", "nome", "tipo", "setor",
             "quantidade_total", "preco_medio", "custo_total",
             "preco_atual", "lucro_prejuizo", "rentabilidade_pct",
             "saldo_atual", "var_dia_pct", "data_cotacao", "atualizado_em",
             "cadastrado", "possui_cotacao"])

    # O peso sempre usa a carteira completa, mesmo quando a tabela está filtrada.
    portfolio_total = sum(r["saldo_atual"] or 0 for r in rows)

    # Filtros
    if tipo and tipo != "Todos":
        rows = [r for r in rows if r["tipo"] == tipo]
    if setor and setor != "Todos":
        rows = [r for r in rows if r["setor"] == setor]

    # Calcular % carteira
    filtered_total = sum(r["saldo_atual"] or 0 for r in rows)
    filtered_cost = sum(r["custo_total"] or 0 for r in rows)
    for r in rows:
        r["pct_carteira"] = portfolio_weight(r["saldo_atual"], portfolio_total)
        if not r["cadastrado"]:
            r["status"] = "sem_cadastro"
        elif not r["possui_cotacao"]:
            r["status"] = "sem_cotacao"
        else:
            r["status"] = "ok"

    return {
        "posicoes": rows,
        "quantidade_posicoes": len(rows),
        "posicoes_com_cotacao": sum(1 for r in rows if r["possui_cotacao"]),
        "posicoes_sem_cotacao": sum(1 for r in rows if not r["possui_cotacao"]),
        "posicoes_sem_cadastro": sum(1 for r in rows if not r["cadastrado"]),
        "custo_total": round(filtered_cost, 2),
        "total_saldo": round(filtered_total, 2),
        "total_carteira": round(portfolio_total, 2),
        "cobertura_completa": all(r["possui_cotacao"] for r in rows),
    }


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

    # Variação do patrimônio observado. Não é TWR: a base atual ainda não
    # registra fluxos de caixa por subperíodo de forma apropriada.
    variacao_patrimonio = percentage_change(
        rows[0]["valor_total"] if rows else None,
        rows[-1]["valor_total"] if rows else None,
    )

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

    return {
        "historico": serialized,
        "twr": None,
        "twr_status": "indisponivel_sem_fluxos_de_caixa",
        "variacao_patrimonio_pct": variacao_patrimonio,
        "aviso": "Histórico reconstruído com posições atuais; não representa performance auditável.",
    }


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
            "valor_por_cota": float(r["valor"] or 0),
            "valor_recebido": None,
            "tipo": r["tipo"],
        })

    return {
        "proventos": serialized,
        "total_12m": None,
        "total_ano": None,
        "total_mes": None,
        "status": "indisponiveis_sem_quantidade_na_data_com",
        "unidade": "valor_por_cota",
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

        # O schema ainda não fornece os insumos necessários para preços justos.
        item["bazin"] = None
        item["graham"] = None

        serialized.append(item)

    ultima_coleta = max(
        (r["data_coleta"] for r in rows if r["data_coleta"]),
        default=None
    )

    return {
        "indicadores": serialized,
        "data_coleta": ultima_coleta.isoformat() if hasattr(ultima_coleta, "isoformat") else str(ultima_coleta) if ultima_coleta else None,
        "precos_justos_status": "indisponiveis_sem_lpa_vpa_e_dividendo_por_acao",
    }


@app.get("/api/qualidade")
async def qualidade():
    """Frescura, cobertura e limitações conhecidas da base exibida."""
    with engine.connect() as conn:
        resumo = _one(conn.execute(text("""
            SELECT
                (SELECT MAX(data) FROM investimentos.cotacoes),
                (SELECT MAX(data_coleta) FROM investimentos.indicadores_fundamentalistas_v2),
                (SELECT MAX(data) FROM investimentos.rentabilidade_diaria),
                (SELECT COUNT(*) FROM investimentos.posicoes WHERE quantidade_total > 0),
                (SELECT COUNT(*) FROM investimentos.posicoes p
                 WHERE p.quantidade_total > 0 AND NOT EXISTS (
                    SELECT 1 FROM investimentos.cotacoes c WHERE c.ticker = p.ticker
                 )),
                (SELECT COUNT(*) FROM investimentos.posicoes p
                 LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
                 WHERE p.quantidade_total > 0 AND a.ticker IS NULL)
        """)).fetchall(), [
            "ultima_cotacao", "ultimo_indicador", "ultimo_snapshot", "posicoes",
            "posicoes_sem_cotacao", "posicoes_sem_cadastro",
        ])

    return {
        **resumo,
        "limitacoes": [
            "Rentabilidade histórica reconstruída com as posições atuais.",
            "TWR indisponível até incorporar aportes e retiradas ao cálculo.",
            "Proventos recebidos indisponíveis; a base atual contém valores por cota.",
            "Patrimônio e lucro consolidados indisponíveis enquanto houver posições sem cotação.",
            "Bazin e Graham indisponíveis sem LPA, VPA e dividendos por ação.",
        ],
    }


@app.get("/health")
async def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "connected"}
