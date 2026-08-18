BEGIN;

CREATE TABLE IF NOT EXISTS investimentos.teses_investimento (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker text NOT NULL,
    versao integer NOT NULL DEFAULT 1 CHECK (versao > 0),
    origem text NOT NULL CHECK (origem IN (
        'ORIGEM_DESCONHECIDA',
        'TESE_ATUAL_RECONSTRUIDA',
        'TESE_CONTEMPORANEA'
    )),
    status text NOT NULL CHECK (status IN (
        'RASCUNHO', 'PUBLICADA', 'SUBSTITUIDA', 'ENCERRADA'
    )),
    resumo text,
    horizonte text,
    riscos jsonb NOT NULL DEFAULT '[]'::jsonb,
    gatilhos_revisao jsonb NOT NULL DEFAULT '[]'::jsonb,
    sugestao_resumo text,
    sugestao_riscos jsonb NOT NULL DEFAULT '[]'::jsonb,
    decisao_em timestamp with time zone,
    sugerida_em timestamp with time zone NOT NULL DEFAULT now(),
    registrada_em timestamp with time zone,
    substitui_id uuid REFERENCES investimentos.teses_investimento(id),
    criado_em timestamp with time zone NOT NULL DEFAULT now(),
    atualizado_em timestamp with time zone NOT NULL DEFAULT now(),
    CHECK (status <> 'PUBLICADA' OR registrada_em IS NOT NULL),
    CHECK (status <> 'RASCUNHO' OR origem = 'ORIGEM_DESCONHECIDA'),
    CHECK (origem <> 'TESE_CONTEMPORANEA' OR decisao_em IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS teses_investimento_ticker_corrente_idx
    ON investimentos.teses_investimento (ticker)
    WHERE status IN ('RASCUNHO', 'PUBLICADA');

INSERT INTO investimentos.teses_investimento (
    ticker, origem, status, sugestao_resumo, sugestao_riscos
)
SELECT
    p.ticker,
    'ORIGEM_DESCONHECIDA',
    'RASCUNHO',
    'Rascunho inicial para revisar o papel de ' || COALESCE(a.nome, p.ticker)
        || ' na carteira. Nao representa a justificativa original da compra.',
    '["Revisao humana dos riscos especificos necessaria"]'::jsonb
FROM investimentos.posicoes p
LEFT JOIN investimentos.ativos a ON a.ticker = p.ticker
WHERE p.quantidade_total > 0
  AND NOT EXISTS (
      SELECT 1 FROM investimentos.teses_investimento t
      WHERE t.ticker = p.ticker AND t.status IN ('RASCUNHO', 'PUBLICADA')
  );

COMMIT;
