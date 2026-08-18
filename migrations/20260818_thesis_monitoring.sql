BEGIN;

CREATE TABLE IF NOT EXISTS investimentos.monitoramentos_tese (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tese_id uuid NOT NULL REFERENCES investimentos.teses_investimento(id),
    data_verificacao date NOT NULL,
    verificado_em timestamp with time zone NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN (
        'BASELINE_CRIADO', 'SEM_MUDANCA_MATERIAL', 'MUDANCA_INFORMATIVA',
        'ACOMPANHAR', 'REVISAO_RECOMENDADA', 'POSSIVEL_INVALIDACAO',
        'DADOS_INSUFICIENTES'
    )),
    snapshot jsonb NOT NULL,
    comparacao jsonb NOT NULL DEFAULT '{}'::jsonb,
    gatilhos jsonb NOT NULL DEFAULT '[]'::jsonb,
    metodologia_versao text NOT NULL DEFAULT 'monitor-v1',
    criado_em timestamp with time zone NOT NULL DEFAULT now(),
    UNIQUE (tese_id, data_verificacao)
);

CREATE INDEX IF NOT EXISTS monitoramentos_tese_status_data_idx
    ON investimentos.monitoramentos_tese (status, data_verificacao DESC);

COMMIT;
