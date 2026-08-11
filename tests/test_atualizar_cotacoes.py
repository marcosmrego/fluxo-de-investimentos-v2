from datetime import date
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import atualizar_cotacoes


def test_yahoo_symbol_uses_b3_suffix():
    assert atualizar_cotacoes.yahoo_symbol("SPCX34") == "SPCX34.SA"
    assert atualizar_cotacoes.yahoo_symbol("ROXO34") == "ROXO34.SA"
    assert atualizar_cotacoes.yahoo_symbol("QQQ", "USD") == "QQQ"
    assert atualizar_cotacoes.yahoo_symbol("O", "USD") == "O"


def test_parse_chart_calculates_daily_variation():
    payload = {
        "chart": {"result": [{
            "timestamp": [1786320000, 1786406400],
            "indicators": {"quote": [{
                "open": [10.0, 11.0], "high": [11.0, 12.0],
                "low": [9.0, 10.0], "close": [10.0, 11.0],
                "volume": [100, 200],
            }]},
        }]}
    }

    rows = atualizar_cotacoes.parse_chart("ROXO34", payload)

    assert len(rows) == 2
    assert rows[-1][0] == "ROXO34"
    assert rows[-1][1] == date(2026, 8, 11)
    assert rows[-1][7] == 10.0


def test_portfolio_query_requires_registered_assets():
    assert "JOIN investimentos.ativos" in atualizar_cotacoes.PORTFOLIO_SQL
    assert "quantidade_total > 0" in atualizar_cotacoes.PORTFOLIO_SQL


def test_usd_quotes_are_normalized_to_brl_and_keep_original_values():
    native_rows = [
        ("O", date(2026, 8, 11), 60.0, 62.0, 59.0, 61.78, 100, None, "yahoo")
    ]

    rows = atualizar_cotacoes.normalizar_para_brl(
        native_rows, "USD", {date(2026, 8, 11): 5.50}
    )

    assert rows[0][2:6] == (330.0, 341.0, 324.5, 339.79)
    assert rows[0][9:] == ("USD", 61.78, 5.50)


def test_brl_quotes_do_not_require_exchange_rates():
    native_rows = [
        ("BOVA11", date(2026, 8, 11), 100.0, 102.0, 99.0, 101.0, 100, None, "yahoo")
    ]

    rows = atualizar_cotacoes.normalizar_para_brl(native_rows, "BRL", {})

    assert rows[0][2:6] == (100.0, 102.0, 99.0, 101.0)
    assert rows[0][9:] == ("BRL", 101.0, 1.0)
