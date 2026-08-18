"""FastAPI — Dashboard Carteira Prof. Marcos (climate-style)."""

import os
import base64
import binascii
import json
import secrets
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import URL, create_engine, text

from dashboard.metrics import percentage_change, portfolio_weight
from dashboard.investment_memory import (
    build_investment_inventory,
    create_initial_thesis_draft,
    generate_fundamental_proposal,
    validate_thesis_publication,
)
from dashboard.portfolio_health import compute_portfolio_health

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


def load_position_thesis_inventory():
    """Load stable thesis records and explicit suggestions for open positions."""
    with engine.connect() as conn:
        positions = _df(conn.execute(text("""
            SELECT p.ticker, p.quantidade_total, a.nome, a.tipo, a.setor,
                   COALESCE(c.fechamento * p.quantidade_total, 0) AS valor,
                   t.origem, t.status, t.resumo, t.horizonte, t.riscos,
                   t.gatilhos_revisao, t.sugestao_resumo, t.sugestao_riscos,
                   t.decisao_em, t.registrada_em
            FROM investimentos.posicoes p
            LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
            LEFT JOIN LATERAL (
                SELECT fechamento FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
            LEFT JOIN LATERAL (
                SELECT origem, status, resumo, horizonte, riscos,
                       gatilhos_revisao, sugestao_resumo, sugestao_riscos,
                       decisao_em, registrada_em
                FROM investimentos.teses_investimento
                WHERE ticker = p.ticker AND status IN ('RASCUNHO', 'PUBLICADA')
                ORDER BY versao DESC LIMIT 1
            ) t ON true
            WHERE p.quantidade_total > 0
            ORDER BY p.ticker
        """)).fetchall(), [
            "ticker", "quantidade", "nome", "tipo", "setor", "valor",
            "origem", "status", "resumo", "horizonte", "riscos",
            "gatilhos_revisao", "sugestao_resumo", "sugestao_riscos",
            "decisao_em", "registrada_em",
        ])

    normalized = [{
        "ticker": row["ticker"],
        "quantity": row["quantidade"],
        "market_value": float(row["valor"] or 0),
        "name": row["nome"],
        "asset_type": row["tipo"],
        "sector": row["setor"],
    } for row in positions]
    theses = []
    for position, row in zip(normalized, positions):
        if not row["origem"]:
            theses.append(create_initial_thesis_draft(position, recorded_at=None))
            continue
        is_published = row["status"] == "PUBLICADA"
        theses.append({
            "ticker": row["ticker"],
            "origin": row["origem"],
            "status": row["status"],
            "summary": row["resumo"] if is_published else row["sugestao_resumo"],
            "horizon": row["horizonte"] if is_published else "A definir na revisao",
            "risks": row["riscos"] if is_published else row["sugestao_riscos"],
            "review_triggers": row["gatilhos_revisao"] if is_published else [
                "Revisao manual da tese"
            ],
            "decision_at": row["decisao_em"].isoformat() if row["decisao_em"] else None,
            "recorded_at": row["registrada_em"].isoformat() if row["registrada_em"] else None,
        })
    return build_investment_inventory(normalized, theses)


def load_automatic_thesis_proposal(ticker: str) -> dict:
    normalized_ticker = ticker.strip().upper()
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT p.ticker, a.nome, a.tipo, a.setor,
                   i.p_l, i.p_vp, i.roe, i.roic, i.dividend_yield,
                   i.div_liq_patrim, i.cres_rec_5a, i.data_coleta
            FROM investimentos.posicoes p
            LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
            LEFT JOIN LATERAL (
                SELECT p_l, p_vp, roe, roic, dividend_yield,
                       div_liq_patrim, cres_rec_5a, data_coleta
                FROM investimentos.indicadores_fundamentalistas_v2
                WHERE ticker = p.ticker ORDER BY data_coleta DESC LIMIT 1
            ) i ON true
            WHERE p.ticker = :ticker AND p.quantidade_total > 0
        """), {"ticker": normalized_ticker}).mappings().first()
    if not row:
        raise LookupError(f"open position not found for {normalized_ticker}")
    return generate_fundamental_proposal({
        "ticker": row["ticker"], "name": row["nome"],
        "asset_type": row["tipo"], "sector": row["setor"],
    }, {
        key: row[key] for key in (
            "p_l", "p_vp", "roe", "roic", "dividend_yield",
            "div_liq_patrim", "cres_rec_5a", "data_coleta",
        )
    } if row["data_coleta"] else None)


class ThesisPublicationRequest(BaseModel):
    origin: str
    summary: str
    horizon: str
    risks: list[str]
    review_triggers: list[str]
    decision_at: str | None = None


def publish_position_thesis(ticker: str, payload: dict) -> dict:
    """Publish the first reviewed version of an existing portfolio draft."""
    normalized_ticker = ticker.strip().upper()
    recorded_at = datetime.now().astimezone().isoformat()
    validated = validate_thesis_publication(payload, recorded_at=recorded_at)
    with engine.begin() as conn:
        row = _publish_position_thesis_with_connection(
            conn, normalized_ticker, validated, recorded_at
        )
    return row


def _publish_position_thesis_with_connection(
    conn, normalized_ticker: str, validated: dict, recorded_at: str
) -> dict:
    """Transactional writer extracted so PostgreSQL behavior can be rollback-tested."""
    draft = conn.execute(text("""
            SELECT id, versao FROM investimentos.teses_investimento
            WHERE ticker = :ticker AND status = 'RASCUNHO'
            FOR UPDATE
    """), {"ticker": normalized_ticker}).mappings().first()
    if not draft:
        raise LookupError(f"open thesis draft not found for {normalized_ticker}")
    conn.execute(text("""
            UPDATE investimentos.teses_investimento
            SET status = 'SUBSTITUIDA', atualizado_em = now()
            WHERE id = :id
    """), {"id": draft["id"]})
    row = conn.execute(text("""
            INSERT INTO investimentos.teses_investimento (
                ticker, versao, origem, status, resumo, horizonte, riscos,
                gatilhos_revisao, decisao_em, registrada_em, substitui_id
            ) VALUES (
                :ticker, :versao, :origem, 'PUBLICADA', :resumo, :horizonte,
                CAST(:riscos AS jsonb), CAST(:gatilhos AS jsonb),
                CAST(:decisao_em AS timestamptz), CAST(:registrada_em AS timestamptz),
                :substitui_id
            )
            RETURNING ticker, versao, origem, status, registrada_em
    """), {
        "ticker": normalized_ticker,
        "versao": draft["versao"],
        "origem": validated["origin"],
        "resumo": validated["summary"],
        "horizonte": validated["horizon"],
        "riscos": json.dumps(validated["risks"]),
        "gatilhos": json.dumps(validated["review_triggers"]),
        "decisao_em": validated["decision_at"],
        "registrada_em": recorded_at,
        "substitui_id": draft["id"],
    }).mappings().first()
    return {
        "ticker": row["ticker"],
        "versao": row["versao"],
        "origin": row["origem"],
        "status": row["status"],
        "recorded_at": row["registrada_em"].isoformat(),
    }


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
                p.ticker, a.nome, a.tipo, a.setor, a.moeda,
                p.quantidade_total, p.preco_medio, p.custo_total,
                c.fechamento AS preco_atual,
                p.preco_medio_origem, p.custo_total_origem,
                c.fechamento_origem AS preco_atual_origem,
                c.taxa_cambio,
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
                SELECT fechamento, fechamento_origem, taxa_cambio,
                       variacao_pct, data FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
            ORDER BY saldo_atual DESC NULLS LAST
        """)).fetchall(),
            ["ticker", "nome", "tipo", "setor", "moeda",
             "quantidade_total", "preco_medio", "custo_total",
             "preco_atual", "preco_medio_origem", "custo_total_origem",
             "preco_atual_origem", "taxa_cambio",
             "lucro_prejuizo", "rentabilidade_pct",
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


@app.get("/api/teses/inventario")
async def teses_inventario():
    """Cobertura inicial de teses para todas as posicoes abertas."""
    return load_position_thesis_inventory()


@app.get("/api/teses/{ticker}/proposta")
async def proposta_automatica_tese(ticker: str):
    try:
        return load_automatic_thesis_proposal(ticker)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/teses/{ticker}/publicar")
async def publicar_tese(ticker: str, request: ThesisPublicationRequest):
    try:
        return publish_position_thesis(ticker, request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@app.get("/api/saude-carteira")
async def saude_carteira():
    """Diagnostico consolidado, explicavel e conservador da carteira atual."""
    with engine.connect() as conn:
        positions = _df(conn.execute(text("""
            SELECT p.ticker, a.setor,
                   COALESCE(c.fechamento * p.quantidade_total, 0) AS valor,
                   (c.fechamento IS NOT NULL) AS possui_cotacao,
                   (a.ticker IS NOT NULL) AS cadastrado
            FROM investimentos.posicoes p
            LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
            LEFT JOIN LATERAL (
                SELECT fechamento FROM investimentos.cotacoes
                WHERE ticker = p.ticker ORDER BY data DESC LIMIT 1
            ) c ON true
            WHERE p.quantidade_total > 0
        """)).fetchall(), ["ticker", "setor", "valor", "possui_cotacao", "cadastrado"])
        returns = conn.execute(text("""
            SELECT rentabilidade FROM investimentos.rentabilidade_diaria
            WHERE rentabilidade IS NOT NULL ORDER BY data DESC LIMIT 252
        """)).fetchall()

    return compute_portfolio_health(
        [{
            "ticker": p["ticker"], "sector": p["setor"],
            "value": float(p["valor"] or 0), "has_quote": p["possui_cotacao"],
            "registered": p["cadastrado"],
        } for p in positions],
        [float(row[0]) for row in reversed(returns)],
        historical_data_reliable=False,
    )


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
