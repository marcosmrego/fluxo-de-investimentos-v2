BEGIN;

CREATE SCHEMA IF NOT EXISTS investimentos_audit;

CREATE TABLE IF NOT EXISTS investimentos_audit.account (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,
    external_account_ref text NOT NULL,
    account_type text NOT NULL,
    display_name text NOT NULL,
    currency_code text NOT NULL CHECK (currency_code ~ '^[A-Z]{3}$'),
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (provider, external_account_ref)
);

CREATE TABLE IF NOT EXISTS investimentos_audit.portfolio (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    description text,
    base_currency_code text NOT NULL
        CHECK (base_currency_code ~ '^[A-Z]{3}$'),
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investimentos_audit.portfolio_account (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id uuid NOT NULL
        REFERENCES investimentos_audit.portfolio(id),
    account_id uuid NOT NULL
        REFERENCES investimentos_audit.account(id),
    ownership_percentage numeric(7, 4) NOT NULL DEFAULT 100
        CHECK (ownership_percentage >= 0 AND ownership_percentage <= 100),
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, account_id)
);

CREATE TABLE IF NOT EXISTS investimentos_audit.instrument (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_symbol text NOT NULL,
    instrument_type text NOT NULL,
    name text NOT NULL,
    currency_code text NOT NULL CHECK (currency_code ~ '^[A-Z]{3}$'),
    exchange_code text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Expression index keeps identity stable on PostgreSQL versions before 15 too.
CREATE UNIQUE INDEX IF NOT EXISTS instrument_identity_idx
    ON investimentos_audit.instrument (
        canonical_symbol, COALESCE(exchange_code, '')
    );

CREATE TABLE IF NOT EXISTS investimentos_audit.instrument_alias (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    instrument_id uuid NOT NULL
        REFERENCES investimentos_audit.instrument(id),
    alias_type text NOT NULL,
    alias_value text NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (alias_type, alias_value)
);

COMMIT;
