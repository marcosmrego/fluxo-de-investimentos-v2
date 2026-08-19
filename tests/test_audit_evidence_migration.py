from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/20260820_002_evidence.sql"


def test_evidence_pipeline_tables_are_idempotent_and_linked():
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "evidence_object",
        "evidence_version",
        "import_run",
        "extracted_record",
        "review",
        "review_decision",
    ):
        assert f"CREATE TABLE IF NOT EXISTS investimentos_audit.{table}" in sql

    assert "REFERENCES investimentos_audit.evidence_object(id)" in sql
    assert "REFERENCES investimentos_audit.evidence_version(id)" in sql
    assert "REFERENCES investimentos_audit.import_run(id)" in sql
    assert "REFERENCES investimentos_audit.extracted_record(id)" in sql
    assert "REFERENCES investimentos_audit.review(id)" in sql
    assert "UNIQUE (evidence_object_id, version_number)" in sql
    assert "UNIQUE (source_system, idempotency_key)" in sql
    assert "UNIQUE (import_run_id, source_record_key)" in sql


def test_evidence_metadata_is_externalized_validated_and_auditable():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "storage_uri text NOT NULL" in sql
    assert "plaintext_sha256 text NOT NULL" in sql
    assert "ciphertext_sha256 text NOT NULL" in sql
    assert "UNIQUE (content_sha256)" not in sql
    assert "octet_length" not in sql.lower()
    assert "pdf_bytes" not in sql.lower()
    assert "bytea" not in sql.lower()
    assert "secret" not in sql.lower()
    assert "amount numeric" in sql
    assert "currency_code text" in sql
    assert "currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'" in sql
    assert "status text NOT NULL" in sql
    assert "CHECK (status IN (" in sql
    assert "created_at timestamp with time zone NOT NULL DEFAULT now()" in sql


def test_run_and_review_lifecycle_timestamps_are_coupled_to_status():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL" in sql
    assert "status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL" in sql
    assert "status IN ('SUCCEEDED', 'FAILED')" in sql
    assert "started_at IS NOT NULL AND finished_at IS NOT NULL" in sql
    assert "status = 'CANCELLED' AND finished_at IS NOT NULL" in sql
    assert "status IN ('ACCEPTED', 'REJECTED')" in sql
    assert "status IN ('PENDING', 'IN_REVIEW', 'NEEDS_CHANGES') AND closed_at IS NULL" in sql


def test_evidence_versions_and_review_decisions_are_immutable():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION investimentos_audit.reject_mutation()" in sql
    assert "BEFORE UPDATE OR DELETE ON investimentos_audit.evidence_version" in sql
    assert "BEFORE UPDATE OR DELETE ON investimentos_audit.review_decision" in sql
