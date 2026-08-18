"""Rollback-only PostgreSQL verification for thesis publication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from dashboard.investment_memory import validate_thesis_publication
from dashboard.main import engine, _publish_position_thesis_with_connection


def verify(ticker: str = "BBAS3") -> None:
    recorded_at = datetime.now().astimezone().isoformat()
    validated = validate_thesis_publication({
        "origin": "TESE_ATUAL_RECONSTRUIDA",
        "summary": "Prova transacional real, temporaria e integralmente revertida.",
        "horizon": "validacao tecnica",
        "risks": ["registro temporario de teste"],
        "review_triggers": ["fim da validacao"],
    }, recorded_at=recorded_at)

    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            result = _publish_position_thesis_with_connection(
                conn, ticker, validated, recorded_at
            )
            rows = conn.execute(text("""
                SELECT status, substitui_id FROM investimentos.teses_investimento
                WHERE ticker = :ticker ORDER BY criado_em
            """), {"ticker": ticker}).mappings().all()
            assert result["status"] == "PUBLICADA"
            assert any(row["status"] == "SUBSTITUIDA" for row in rows)
            assert any(
                row["status"] == "PUBLICADA" and row["substitui_id"] is not None
                for row in rows
            )
        finally:
            transaction.rollback()

    with engine.connect() as conn:
        statuses = conn.execute(text("""
            SELECT status FROM investimentos.teses_investimento
            WHERE ticker = :ticker AND status IN ('RASCUNHO', 'PUBLICADA')
        """), {"ticker": ticker}).scalars().all()
    assert statuses == ["RASCUNHO"]
    print(f"thesis publication rollback verification passed for {ticker}")


if __name__ == "__main__":
    verify()
