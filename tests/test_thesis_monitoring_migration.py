from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monitoring_history_is_idempotent_and_auditable():
    sql = (ROOT / "migrations/20260818_thesis_monitoring.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS investimentos.monitoramentos_tese" in sql
    assert "snapshot jsonb NOT NULL" in sql
    assert "gatilhos jsonb NOT NULL" in sql
    assert "UNIQUE (tese_id, data_verificacao)" in sql
    assert "BASELINE_CRIADO" in sql
    assert "DADOS_INSUFICIENTES" in sql


def test_cron_runs_monitoring_after_market_data_update():
    cron = (ROOT / "deploy/investimentos-jobs.cron").read_text(encoding="utf-8")

    assert "investimentos-monitoramento" in cron
    assert "scripts/monitorar_teses.py" in cron
