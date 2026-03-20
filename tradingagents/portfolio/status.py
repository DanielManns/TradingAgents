"""Portfolio status evaluation: pick, portfolio, and historical performance."""

from __future__ import annotations

from typing import Callable

from tradingagents.portfolio.models import Pick, Portfolio, PortfolioState

PriceFetcher = Callable[[str, str | None], float | None]


class PickEvaluator:
    """Evaluates a single pick: fetches current price and computes pct_change."""

    def __init__(self, price_fetcher: PriceFetcher):
        self.price_fetcher = price_fetcher

    def evaluate(self, pick: Pick) -> tuple[float, float] | None:
        """Compute current_price and pct_change for a pick.

        Returns (current_price, pct_change) or None if entry_price is missing
        or current price is unavailable.
        """
        if pick.entry_price is None or pick.entry_price == 0:
            return None

        current_price = self.price_fetcher(pick.ticker, None)
        if current_price is None:
            return None

        pct = (current_price - pick.entry_price) / pick.entry_price * 100.0
        return current_price, round(pct, 2)


class PortfolioEvaluator:
    """Evaluates a portfolio: aggregates pick performance and compares to benchmark."""

    def __init__(self, price_fetcher: PriceFetcher):
        self.pick_evaluator = PickEvaluator(price_fetcher)
        self.price_fetcher = price_fetcher

    def evaluate(self, portfolio: Portfolio) -> tuple[list[Pick], float, float | None]:
        """Compute enriched picks, portfolio_return, and spy_return.

        Returns (evaluated_picks, portfolio_return, spy_return).
        """
        evaluated_picks = []
        for pick in portfolio.picks:
            result = self.pick_evaluator.evaluate(pick)
            if result is not None:
                current_price, pct_change = result
                evaluated_picks.append(pick.model_copy(update={
                    "current_price": current_price,
                    "pct_change": pct_change,
                }))

        avg_pct = round(self._avg_pct(evaluated_picks), 2)
        spy_pct = self._spy_pct_change(portfolio.date)

        return evaluated_picks, avg_pct, spy_pct

    @staticmethod
    def _avg_pct(picks: list[Pick]) -> float:
        """Equal-weighted average performance."""
        if not picks:
            return 0.0
        return sum(p.pct_change for p in picks if p.pct_change is not None) / len(picks)

    def _spy_pct_change(self, pick_date: str) -> float | None:
        """SPY performance since pick_date as benchmark."""
        price_then = self.price_fetcher("SPY", pick_date)
        price_now = self.price_fetcher("SPY", None)
        if price_then is None or price_now is None or price_then == 0:
            return None
        return round((price_now - price_then) / price_then * 100.0, 2)


class HistoricalEvaluator:
    """Evaluates all-time performance across rebalances using TWR."""

    @staticmethod
    def _period_return(portfolio: Portfolio) -> float | None:
        """Compute equal-weighted period return treating current_price as exit_price."""
        pick_returns = []
        for p in portfolio.picks:
            if p.entry_price and p.current_price is not None:
                pick_returns.append((p.current_price - p.entry_price) / p.entry_price)
        return sum(pick_returns) / len(pick_returns) if pick_returns else None

    @staticmethod
    def evaluate(state: PortfolioState, current_portfolio: Portfolio | None = None) -> float | None:
        """Compute Time-Weighted Return from archived snapshots plus the live period.

        TWR = (1 + r1) * (1 + r2) * ... - 1
        Returns None if no period returns exist.

        Args:
            state: Portfolio state with historical snapshots.
            current_portfolio: Evaluated portfolio with live current_price on
                each pick. current_price is treated as exit_price to derive
                the current (unarchived) period return.
        """
        returns = [s.portfolio_return for s in state.past_portfolios if s.portfolio_return is not None]
        if current_portfolio is not None:
            live = HistoricalEvaluator._period_return(current_portfolio)
            if live is not None:
                returns.append(live)
        if not returns:
            return None

        twr = 1.0
        for r in returns:
            twr *= 1.0 + r
        return round(twr - 1.0, 4)
