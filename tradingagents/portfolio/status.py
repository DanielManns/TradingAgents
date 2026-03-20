"""Portfolio status: current performance of held stocks."""

from __future__ import annotations

from typing import Callable

from tradingagents.portfolio.models import Pick, Portfolio

PriceFetcher = Callable[[str, str | None], float | None]


class PortfolioStatus:
    """Builds performance entries for a portfolio from a Portfolio object."""

    def __init__(self, price_fetcher: PriceFetcher):
        self.price_fetcher = price_fetcher

    def build(self, portfolio: Portfolio) -> list[Pick]:
        """Build pick list with current prices and performance.

        Returns:
            List of Pick with entry_price, current_price, pct_change set.
            Tickers with missing prices are skipped.
        """
        pick_date = portfolio.date
        entries: list[Pick] = []

        for pick in portfolio.picks:
            ticker = pick.ticker
            entry_price = self.price_fetcher(ticker, pick_date)
            current_price = self.price_fetcher(ticker, None)

            if entry_price is None or current_price is None:
                continue
            if entry_price == 0:
                continue

            pct = (current_price - entry_price) / entry_price * 100.0
            entries.append(pick.model_copy(update={
                "entry_date": pick_date,
                "entry_price": entry_price,
                "current_price": current_price,
                "pct_change": round(pct, 2),
            }))

        return entries

    def portfolio_avg_pct(self, entries: list[Pick]) -> float:
        """Equal-weighted average performance."""
        if not entries:
            return 0.0
        return sum(e.pct_change for e in entries if e.pct_change is not None) / len(entries)

    def spy_pct_change(self, pick_date: str) -> float | None:
        """SPY performance since pick_date as benchmark."""
        price_then = self.price_fetcher("SPY", pick_date)
        price_now = self.price_fetcher("SPY", None)
        if price_then is None or price_now is None or price_then == 0:
            return None
        return round((price_now - price_then) / price_then * 100.0, 2)


def compute_twr(output_dir: str = "portfolio_data", portfolio: str = "default") -> float | None:
    """Compute the Time-Weighted Return (TWR) over all archived periods.

    Reads period_returns from state.json snapshots.
    TWR = (1 + r1) * (1 + r2) * ... - 1
    """
    from tradingagents.portfolio.persistence import load_state

    state = load_state(output_dir, portfolio)
    returns = [s.portfolio_return for s in state.snapshots if s.portfolio_return is not None]
    if not returns:
        return None

    twr = 1.0
    for r in returns:
        twr *= 1.0 + r
    return round(twr - 1.0, 4)
