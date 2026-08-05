"""Pure financial helpers used by the API and covered by unit tests.

These functions intentionally avoid calling portfolio appreciation a TWR. A real
time-weighted return requires cash-flow-aware subperiod returns, data that the
current schema does not expose yet.
"""

from decimal import Decimal


def percentage_change(initial: object, final: object) -> float | None:
    """Return the percentage change between two values, or None if undefined."""
    if initial is None or final is None:
        return None
    start = Decimal(str(initial))
    end = Decimal(str(final))
    if start == 0:
        return None
    return round(float((end / start - 1) * 100), 2)


def portfolio_weight(value: object, portfolio_total: object) -> float:
    """Return an asset's weight against the complete (unfiltered) portfolio."""
    amount = Decimal(str(value or 0))
    total = Decimal(str(portfolio_total or 0))
    if total <= 0:
        return 0.0
    return round(float(amount / total * 100), 2)
