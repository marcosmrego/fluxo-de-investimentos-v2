BEGIN;

CREATE OR REPLACE FUNCTION investimentos.proteger_tese_publicada()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.status IN ('PUBLICADA', 'SUBSTITUIDA') THEN
        RAISE EXCEPTION 'tese publicada e imutavel';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status IN ('PUBLICADA', 'SUBSTITUIDA') THEN
        IF NOT (
            OLD.status = 'PUBLICADA' AND NEW.status = 'SUBSTITUIDA'
            AND (to_jsonb(NEW) - ARRAY['status', 'atualizado_em'])
                IS NOT DISTINCT FROM
                (to_jsonb(OLD) - ARRAY['status', 'atualizado_em'])
        ) THEN
            RAISE EXCEPTION 'conteudo de tese publicada e imutavel';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS proteger_tese_publicada_trigger
    ON investimentos.teses_investimento;
CREATE TRIGGER proteger_tese_publicada_trigger
BEFORE UPDATE OR DELETE ON investimentos.teses_investimento
FOR EACH ROW EXECUTE FUNCTION investimentos.proteger_tese_publicada();

COMMIT;
