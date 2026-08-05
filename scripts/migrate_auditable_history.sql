-- Modelo aditivo para performance, renda passiva e fiscalidade auditaveis.
-- Este arquivo prepara a estrutura; nao reconstrui historico sem fonte oficial.
-- Execute em transacao e somente depois de backup validado.

BEGIN;

CREATE TABLE IF NOT EXISTS investimentos.fluxos_caixa (
    id uuid PRIMARY KEY,
    data date NOT NULL,
    tipo text NOT NULL CHECK (tipo IN (
        'APORTE', 'RETIRADA', 'PROVENTO', 'TAXA', 'IMPOSTO', 'OUTRO'
    )),
    valor numeric(18, 2) NOT NULL CHECK (valor > 0),
    ticker text,
    nota_id uuid REFERENCES investimentos.notas_negociacao(id),
    fonte text NOT NULL,
    referencia_externa text,
    criado_em timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (fonte, referencia_externa)
);

CREATE INDEX IF NOT EXISTS fluxos_caixa_data_idx
    ON investimentos.fluxos_caixa (data);

CREATE TABLE IF NOT EXISTS investimentos.custodia_diaria (
    data date NOT NULL,
    ticker text NOT NULL,
    quantidade numeric(18, 6) NOT NULL CHECK (quantidade >= 0),
    custo_total numeric(18, 2) NOT NULL CHECK (custo_total >= 0),
    fonte text NOT NULL,
    criado_em timestamp without time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (data, ticker)
);

CREATE TABLE IF NOT EXISTS investimentos.performance_diaria_v2 (
    data date PRIMARY KEY,
    patrimonio_inicial numeric(18, 2) NOT NULL,
    fluxo_externo_liquido numeric(18, 2) NOT NULL DEFAULT 0,
    patrimonio_final numeric(18, 2) NOT NULL,
    retorno_periodo numeric(18, 10),
    cobertura_completa boolean NOT NULL DEFAULT false,
    metodologia text NOT NULL DEFAULT 'TWR',
    criado_em timestamp without time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investimentos.proventos_recebidos (
    id uuid PRIMARY KEY,
    ticker text NOT NULL,
    data_com date,
    data_pagamento date NOT NULL,
    quantidade_elegivel numeric(18, 6) NOT NULL CHECK (quantidade_elegivel >= 0),
    valor_por_cota numeric(18, 8) NOT NULL CHECK (valor_por_cota >= 0),
    valor_recebido numeric(18, 2) NOT NULL CHECK (valor_recebido >= 0),
    tipo text,
    fonte text NOT NULL,
    referencia_externa text,
    criado_em timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (fonte, referencia_externa)
);

COMMIT;
