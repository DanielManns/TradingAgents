"""Portfolio evaluation: pick, portfolio, and historical performance."""

from __future__ import annotations

from typing import Callable

from tradingagents.portfolio.models import Pick, PortfolioState

PriceFetcher = Callable[[str, str | None], float | None]


def evaluate_pick(pick: Pick, price_fetcher: PriceFetcher) -> tuple[float, float] | None:
    """Compute current_price and pct_change for a pick.

    Returns (current_price, pct_change) or None if entry_price is missing
    or current price is unavailable.
    """
    if pick.entry_price is None or pick.entry_price == 0:
        return None

    current_price = price_fetcher(pick.ticker, None)
    if current_price is None:
        return None

    pct = (current_price - pick.entry_price) / pick.entry_price * 100.0
    return current_price, round(pct, 2)


def evaluate_picks(picks: list[Pick], price_fetcher: PriceFetcher) -> dict[str, tuple[float, float]]:
    """Evaluate all picks, returning a ticker-keyed map of results.

    Returns {ticker: (current_price, pct_change)} for picks that could be evaluated.
    """
    results: dict[str, tuple[float, float]] = {}
    for pick in picks:
        result = evaluate_pick(pick, price_fetcher)
        if result is not None:
            results[pick.ticker] = result
    return results


def evaluate_portfolio(pct_changes: list[float], date: str, price_fetcher: PriceFetcher) -> tuple[float, float | None]:
    """Compute portfolio_return and spy_return.

    Args:
        pct_changes: Per-pick percentage changes.
        date: Portfolio pick date (for SPY benchmark).
        price_fetcher: Callable to fetch prices.

    Returns (portfolio_return, spy_return).
    """
    avg_pct = round(sum(pct_changes) / len(pct_changes), 2) if pct_changes else 0.0
    spy_pct = _spy_pct_change(date, price_fetcher)
    return avg_pct, spy_pct


def evaluate_portfolio_state(state: PortfolioState, live_period_return: float | None = None) -> float | None:
    """Compute Time-Weighted Return from archived snapshots plus the live period.

    TWR = (1 + r1) * (1 + r2) * ... - 1
    Returns None if no period returns exist.

    Args:
        state: Portfolio state with historical snapshots.
        live_period_return: Current (unarchived) period return as a fraction
            (e.g. 0.05 for 5%). Appended to archived returns for TWR.
    """
    returns = [s.portfolio_return for s in state.past_portfolios if s.portfolio_return is not None]
    if live_period_return is not None:
        returns.append(live_period_return)
    if not returns:
        return None

    twr = 1.0
    for r in returns:
        twr *= 1.0 + r
    return round(twr - 1.0, 4)


def live_period_return(picks: list[Pick], eval_results: dict[str, tuple[float, float]]) -> float | None:
    """Compute equal-weighted period return from entry_price to current_price.

    Args:
        picks: Original picks with entry_price.
        eval_results: {ticker: (current_price, pct_change)} from evaluate_picks.

    Returns fractional return (e.g. 0.05 for 5%) or None if no picks qualify.
    """
    pick_returns = []
    for p in picks:
        if p.entry_price and p.ticker in eval_results:
            current_price, _ = eval_results[p.ticker]
            pick_returns.append((current_price - p.entry_price) / p.entry_price)
    return sum(pick_returns) / len(pick_returns) if pick_returns else None


def _spy_pct_change(pick_date: str, price_fetcher: PriceFetcher) -> float | None:
    """SPY performance since pick_date as benchmark."""
    price_then = price_fetcher("SPY", pick_date)
    price_now = price_fetcher("SPY", None)
    if price_then is None or price_now is None or price_then == 0:
        return None
    return round((price_now - price_then) / price_then * 100.0, 2)
