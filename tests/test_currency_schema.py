from pathlib import Path


def test_currency_migration_preserves_brl_defaults_and_native_values():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "20260811_multi_currency.sql"
    ).read_text(encoding="utf-8")

    assert "moeda VARCHAR(3) NOT NULL DEFAULT 'BRL'" in migration
    assert "fechamento_origem" in migration
    assert "taxa_cambio" in migration
    assert "preco_medio_origem" in migration
