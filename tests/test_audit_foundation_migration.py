from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/20260820_001_audit_foundation.sql"


def test_audit_foundation_is_additive_idempotent_and_scoped():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE SCHEMA IF NOT EXISTS investimentos_audit" in sql
    assert "CREATE TABLE IF NOT EXISTS investimentos_audit.account" in sql
    assert "CREATE TABLE IF NOT EXISTS investimentos_audit.portfolio" in sql
    assert "CREATE TABLE IF NOT EXISTS investimentos_audit.portfolio_account" in sql
    assert "CREATE TABLE IF NOT EXISTS investimentos_audit.instrument" in sql
    assert "CREATE TABLE IF NOT EXISTS investimentos_audit.instrument_alias" in sql
    assert "gen_random_uuid()" in sql
    assert "timestamp with time zone NOT NULL DEFAULT now()" in sql
    assert "currency_code text" in sql
    assert "currency_code ~ '^[A-Z]{3}$'" in sql
    assert "UNIQUE (portfolio_id, account_id)" in sql
    assert "UNIQUE (alias_type, alias_value)" in sql
    assert "CREATE TABLE investimentos." not in sql
    assert "ALTER TABLE investimentos." not in sql


def test_foundation_relations_have_foreign_keys_and_numeric_guards():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "REFERENCES investimentos_audit.portfolio(id)" in sql
    assert "REFERENCES investimentos_audit.account(id)" in sql
    assert "REFERENCES investimentos_audit.instrument(id)" in sql
    assert "ownership_percentage numeric" in sql
    assert "ownership_percentage >= 0" in sql
    assert "ownership_percentage <= 100" in sql


def test_instrument_identity_is_unique_even_without_exchange():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE UNIQUE INDEX IF NOT EXISTS instrument_identity_idx" in sql
    assert "COALESCE(exchange_code, '')" in sql
