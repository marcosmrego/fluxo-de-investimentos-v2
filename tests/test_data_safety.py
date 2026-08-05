import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from data_availability import (
    unavailable_passive_income_result,
    unavailable_tax_result,
)


def test_tax_estimate_is_disabled_without_fiscal_ledger():
    result = unavailable_tax_result()

    assert result["disponivel"] is False
    assert result["status"] == "indisponivel_sem_livro_fiscal"
    assert "resumo" not in result


def test_passive_income_is_disabled_without_historical_positions():
    result = unavailable_passive_income_result()

    assert result["disponivel"] is False
    assert result["status"] == "indisponivel_sem_posicao_na_data_com"
    assert result["proventos_por_mes"] == []
    assert result["proventos_por_ativo"] == []
