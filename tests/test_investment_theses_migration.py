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
    assert "status <> 'RASCUNHO' OR origem = 'ORIGEM_DESCONHECIDA'" in sql


def test_thesis_migration_seeds_open_positions_as_unknown_not_reconstructed():
    sql = (ROOT / "migrations/20260818_investment_theses.sql").read_text(
        encoding="utf-8"
    )

    assert "FROM investimentos.posicoes p" in sql
    assert "p.quantidade_total > 0" in sql
    assert "'ORIGEM_DESCONHECIDA'" in sql
    assert "'RASCUNHO'" in sql


def test_published_thesis_versions_are_protected_by_database_trigger():
    sql = (ROOT / "migrations/20260818_thesis_immutability.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE OR REPLACE FUNCTION investimentos.proteger_tese_publicada" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "conteudo de tese publicada e imutavel" in sql
