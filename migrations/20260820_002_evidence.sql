BEGIN;

CREATE SCHEMA IF NOT EXISTS investimentos_audit;

CREATE TABLE IF NOT EXISTS investimentos_audit.evidence_object (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL,
    source_object_key text NOT NULL,
    evidence_type text NOT NULL,
    title text,
    occurred_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (source_system, source_object_key)
);

CREATE TABLE IF NOT EXISTS investimentos_audit.evidence_version (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_object_id uuid NOT NULL
        REFERENCES investimentos_audit.evidence_object(id),
    version_number integer NOT NULL CHECK (version_number > 0),
    storage_uri text NOT NULL,
    plaintext_sha256 text NOT NULL
        CHECK (plaintext_sha256 ~ '^[0-9a-f]{64}$'),
    ciphertext_sha256 text NOT NULL
        CHECK (ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
    media_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    captured_at timestamp with time zone NOT NULL DEFAULT now(),
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (evidence_object_id, version_number)
);

CREATE TABLE IF NOT EXISTS investimentos_audit.import_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system text NOT NULL,
    idempotency_key text NOT NULL,
    status text NOT NULL CHECK (status IN (
        'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'
    )),
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    error_summary text,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (source_system, idempotency_key),
    CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at),
    CHECK (
        (status = 'PENDING' AND started_at IS NULL AND finished_at IS NULL)
        OR (status = 'RUNNING' AND started_at IS NOT NULL AND finished_at IS NULL)
        OR (
            status IN ('SUCCEEDED', 'FAILED')
            AND started_at IS NOT NULL AND finished_at IS NOT NULL
        )
        OR (status = 'CANCELLED' AND finished_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS investimentos_audit.extracted_record (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_run_id uuid NOT NULL
        REFERENCES investimentos_audit.import_run(id),
    evidence_version_id uuid NOT NULL
        REFERENCES investimentos_audit.evidence_version(id),
    source_record_key text NOT NULL,
    record_type text NOT NULL,
    account_id uuid REFERENCES investimentos_audit.account(id),
    portfolio_id uuid REFERENCES investimentos_audit.portfolio(id),
    instrument_id uuid REFERENCES investimentos_audit.instrument(id),
    occurred_at timestamp with time zone,
    amount numeric(30, 10),
    quantity numeric(30, 10),
    currency_code text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    CHECK (currency_code IS NULL OR currency_code ~ '^[A-Z]{3}$'),
    UNIQUE (import_run_id, source_record_key)
);

CREATE TABLE IF NOT EXISTS investimentos_audit.review (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    extracted_record_id uuid NOT NULL
        REFERENCES investimentos_audit.extracted_record(id),
    status text NOT NULL CHECK (status IN (
        'PENDING', 'IN_REVIEW', 'ACCEPTED', 'REJECTED', 'NEEDS_CHANGES'
    )),
    assigned_to text,
    opened_at timestamp with time zone NOT NULL DEFAULT now(),
    closed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (extracted_record_id),
    CHECK (closed_at IS NULL OR closed_at >= opened_at),
    CHECK (
        (status IN ('ACCEPTED', 'REJECTED') AND closed_at IS NOT NULL)
        OR (status IN ('PENDING', 'IN_REVIEW', 'NEEDS_CHANGES') AND closed_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS investimentos_audit.review_decision (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id uuid NOT NULL REFERENCES investimentos_audit.review(id),
    decision text NOT NULL CHECK (decision IN (
        'ACCEPT', 'REJECT', 'REQUEST_CHANGES', 'COMMENT'
    )),
    decided_by text NOT NULL,
    rationale text,
    created_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION investimentos_audit.reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit history rows are immutable';
END;
$$;

DROP TRIGGER IF EXISTS evidence_version_reject_mutation
    ON investimentos_audit.evidence_version;
CREATE TRIGGER evidence_version_reject_mutation
BEFORE UPDATE OR DELETE ON investimentos_audit.evidence_version
FOR EACH ROW EXECUTE FUNCTION investimentos_audit.reject_mutation();

DROP TRIGGER IF EXISTS review_decision_reject_mutation
    ON investimentos_audit.review_decision;
CREATE TRIGGER review_decision_reject_mutation
BEFORE UPDATE OR DELETE ON investimentos_audit.review_decision
FOR EACH ROW EXECUTE FUNCTION investimentos_audit.reject_mutation();

COMMIT;
