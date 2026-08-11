BEGIN;

ALTER TABLE investimentos.ativos
    ADD COLUMN IF NOT EXISTS moeda VARCHAR(3) NOT NULL DEFAULT 'BRL';

ALTER TABLE investimentos.posicoes
    ADD COLUMN IF NOT EXISTS moeda VARCHAR(3) NOT NULL DEFAULT 'BRL',
    ADD COLUMN IF NOT EXISTS preco_medio_origem NUMERIC(18, 6),
    ADD COLUMN IF NOT EXISTS custo_total_origem NUMERIC(18, 2),
    ADD COLUMN IF NOT EXISTS taxa_cambio_custo NUMERIC(18, 6);

UPDATE investimentos.posicoes
SET preco_medio_origem = COALESCE(preco_medio_origem, preco_medio),
    custo_total_origem = COALESCE(custo_total_origem, custo_total),
    taxa_cambio_custo = COALESCE(taxa_cambio_custo, 1)
WHERE preco_medio_origem IS NULL
   OR custo_total_origem IS NULL
   OR taxa_cambio_custo IS NULL;

ALTER TABLE investimentos.cotacoes
    ADD COLUMN IF NOT EXISTS moeda VARCHAR(3) NOT NULL DEFAULT 'BRL',
    ADD COLUMN IF NOT EXISTS fechamento_origem NUMERIC(18, 6),
    ADD COLUMN IF NOT EXISTS taxa_cambio NUMERIC(18, 6) NOT NULL DEFAULT 1;

UPDATE investimentos.cotacoes
SET fechamento_origem = COALESCE(fechamento_origem, fechamento)
WHERE fechamento_origem IS NULL;

COMMIT;
