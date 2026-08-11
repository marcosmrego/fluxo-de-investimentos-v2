from datetime import date
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import atualizar_cotacoes


def test_yahoo_symbol_uses_b3_suffix():
    assert atualizar_cotacoes.yahoo_symbol("SPCX34") == "SPCX34.SA"
    assert atualizar_cotacoes.yahoo_symbol("ROXO34") == "ROXO34.SA"
    assert atualizar_cotacoes.yahoo_symbol("QQQ") == "QQQ"


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
