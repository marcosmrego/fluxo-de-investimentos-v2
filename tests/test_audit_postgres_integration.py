import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("AUDIT_TEST_DATABASE_URL")


def _safe_test_database_url() -> str:
    if not DATABASE_URL:
        pytest.skip("AUDIT_TEST_DATABASE_URL is not set; PostgreSQL integration is opt-in")
    database_name = urlparse(DATABASE_URL).path.lstrip("/").lower()
    if "audit_test" not in database_name:
        pytest.fail("AUDIT_TEST_DATABASE_URL database name must contain 'audit_test'")
    return DATABASE_URL


def test_audit_migrations_apply_twice_and_enforce_database_contracts():
    psycopg2 = pytest.importorskip("psycopg2")
    connection = psycopg2.connect(_safe_test_database_url())
    connection.autocommit = True
    foundation = (ROOT / "migrations/20260820_001_audit_foundation.sql").read_text(
        encoding="utf-8"
    )
    evidence = (ROOT / "migrations/20260820_002_evidence.sql").read_text(
        encoding="utf-8"
    )

    try:
        with connection.cursor() as cursor:
            for _ in range(2):
                cursor.execute(foundation)
                cursor.execute(evidence)

            cursor.execute(
                """
                SELECT count(*)
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'investimentos_audit'
                  AND t.tgname IN (
                    'evidence_version_reject_mutation',
                    'review_decision_reject_mutation'
                  )
                  AND NOT t.tgisinternal
                """
            )
            assert cursor.fetchone() == (2,)

            cursor.execute(
                """
                SELECT count(*)
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'investimentos_audit'
                  AND c.relname IN ('import_run', 'review')
                  AND con.contype = 'c'
                """
            )
            assert cursor.fetchone()[0] >= 6

            source_key = str(uuid4())
            cursor.execute(
                """
                INSERT INTO investimentos_audit.evidence_object
                    (source_system, source_object_key, evidence_type)
                VALUES ('integration', %s, 'document') RETURNING id
                """,
                (source_key,),
            )
            evidence_object_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO investimentos_audit.evidence_version
                    (evidence_object_id, version_number, storage_uri,
                     plaintext_sha256, ciphertext_sha256, media_type, size_bytes)
                VALUES (%s, 1, %s, %s, %s, 'application/pdf', 1) RETURNING id
                """,
                (evidence_object_id, f"test://{source_key}", "a" * 64, "b" * 64),
            )
            version_id = cursor.fetchone()[0]

            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    "UPDATE investimentos_audit.evidence_version SET size_bytes = 2 WHERE id = %s",
                    (version_id,),
                )
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    "DELETE FROM investimentos_audit.evidence_version WHERE id = %s",
                    (version_id,),
                )
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    """
                    INSERT INTO investimentos_audit.import_run
                        (source_system, idempotency_key, status)
                    VALUES ('integration', %s, 'SUCCEEDED')
                    """,
                    (str(uuid4()),),
                )
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    """
                    INSERT INTO investimentos_audit.import_run
                        (source_system, idempotency_key, status, started_at)
                    VALUES ('integration', %s, 'PENDING', now())
                    """,
                    (str(uuid4()),),
                )
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    """
                    INSERT INTO investimentos_audit.import_run
                        (source_system, idempotency_key, status)
                    VALUES ('integration', %s, 'RUNNING')
                    """,
                    (str(uuid4()),),
                )
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    """
                    INSERT INTO investimentos_audit.import_run
                        (source_system, idempotency_key, status, finished_at)
                    VALUES ('integration', %s, 'FAILED', now())
                    """,
                    (str(uuid4()),),
                )

            cursor.execute(
                """
                INSERT INTO investimentos_audit.import_run
                    (source_system, idempotency_key, status, started_at)
                VALUES ('integration', %s, 'RUNNING', now()) RETURNING id
                """,
                (str(uuid4()),),
            )
            import_run_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO investimentos_audit.extracted_record
                    (import_run_id, evidence_version_id, source_record_key,
                     record_type)
                VALUES (%s, %s, %s, 'transaction') RETURNING id
                """,
                (import_run_id, version_id, str(uuid4())),
            )
            extracted_record_id = cursor.fetchone()[0]
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    """
                    INSERT INTO investimentos_audit.review
                        (extracted_record_id, status)
                    VALUES (%s, 'ACCEPTED')
                    """,
                    (extracted_record_id,),
                )

            cursor.execute(
                """
                INSERT INTO investimentos_audit.review
                    (extracted_record_id, status)
                VALUES (%s, 'IN_REVIEW') RETURNING id
                """,
                (extracted_record_id,),
            )
            review_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO investimentos_audit.review_decision
                    (review_id, decision, decided_by)
                VALUES (%s, 'COMMENT', 'integration-test') RETURNING id
                """,
                (review_id,),
            )
            decision_id = cursor.fetchone()[0]
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    """
                    UPDATE investimentos_audit.review_decision
                    SET rationale = 'changed' WHERE id = %s
                    """,
                    (decision_id,),
                )
            with pytest.raises(psycopg2.Error):
                cursor.execute(
                    "DELETE FROM investimentos_audit.review_decision WHERE id = %s",
                    (decision_id,),
                )
    finally:
        connection.close()
