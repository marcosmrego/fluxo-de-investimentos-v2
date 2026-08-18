"""Daily, idempotent monitoring of every published investment thesis."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

from dashboard.thesis_monitoring import evaluate_thesis_monitoring
from scripts.db_utils import DB_CONFIG


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def run() -> dict:
    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    counts: dict[str, int] = {}
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT t.id AS tese_id, t.ticker, t.registrada_em, a.tipo,
                       c.fechamento AS price, c.variacao_pct AS daily_change_pct,
                       i.p_l, i.p_vp, i.roe, i.roic, i.div_liq_patrim,
                       i.dividend_yield, i.data_coleta,
                       m.snapshot AS baseline
                FROM investimentos.teses_investimento t
                LEFT JOIN investimentos.ativos a ON a.ticker = t.ticker
                LEFT JOIN LATERAL (
                    SELECT fechamento, variacao_pct FROM investimentos.cotacoes
                    WHERE ticker = t.ticker ORDER BY data DESC LIMIT 1
                ) c ON true
                LEFT JOIN LATERAL (
                    SELECT p_l, p_vp, roe, roic, div_liq_patrim,
                           dividend_yield, data_coleta
                    FROM investimentos.indicadores_fundamentalistas_v2
                    WHERE ticker = t.ticker ORDER BY data_coleta DESC LIMIT 1
                ) i ON true
                LEFT JOIN LATERAL (
                    SELECT snapshot FROM investimentos.monitoramentos_tese
                    WHERE tese_id = t.id AND status = 'BASELINE_CRIADO'
                    ORDER BY data_verificacao ASC LIMIT 1
                ) m ON true
                WHERE t.status = 'PUBLICADA'
                  AND NOT EXISTS (
                      SELECT 1 FROM investimentos.monitoramentos_tese hoje
                      WHERE hoje.tese_id = t.id AND hoje.data_verificacao = %s
                  )
                ORDER BY t.ticker
            """, (today,))
            for row in cur.fetchall():
                snapshot = {
                    key: row.get(key) for key in (
                        "price", "daily_change_pct", "p_l", "p_vp", "roe",
                        "roic", "div_liq_patrim", "dividend_yield",
                    )
                }
                snapshot["data_age_days"] = (
                    (today - row["data_coleta"]).days if row.get("data_coleta") else None
                )
                days = (today - row["registrada_em"].date()).days
                result = evaluate_thesis_monitoring(
                    row.get("baseline"), snapshot, row.get("tipo"), days
                )
                cur.execute("""
                    INSERT INTO investimentos.monitoramentos_tese (
                        tese_id, data_verificacao, status, snapshot, comparacao, gatilhos
                    ) VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (tese_id, data_verificacao) DO NOTHING
                """, (
                    row["tese_id"], today, result["status"],
                    json.dumps(snapshot, default=_json_default),
                    json.dumps(result["changes"]), json.dumps(result["triggers"]),
                ))
                counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {"date": today.isoformat(), "evaluated": sum(counts.values()), "statuses": counts}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
