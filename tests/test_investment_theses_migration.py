from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_thesis_migration_persists_unknown_drafts_and_version_fields():
    sql = (ROOT / "migrations/20260818_investment_theses.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS investimentos.teses_investimento" in sql
    assert "ORIGEM_DESCONHECIDA" in sql
    assert "TESE_ATUAL_RECONSTRUIDA" in sql
    assert "TESE_CONTEMPORANEA" in sql
    assert "versao integer NOT NULL" in sql
    assert "sugerida_em timestamp with time zone" in sql
    assert "registrada_em timestamp with time zone" in sql
    assert "CREATE UNIQUE INDEX" in sql


def test_thesis_migration_seeds_open_positions_as_unknown_not_reconstructed():
    sql = (ROOT / "migrations/20260818_investment_theses.sql").read_text(
        encoding="utf-8"
    )

    assert "FROM investimentos.posicoes p" in sql
    assert "p.quantidade_total > 0" in sql
    assert "'ORIGEM_DESCONHECIDA'" in sql
    assert "'RASCUNHO'" in sql
