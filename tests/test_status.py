"""Tests for status evaluation: pick, portfolio, and historical performance."""

from __future__ import annotations

import pytest

from tradingagents.portfolio.models import Pick, Portfolio, PortfolioState, RebalanceAction, RebalanceEntry, RebalanceEvent
from tradingagents.portfolio.persistence import save_portfolio, load_portfolio, archive_rebalance
from tradingagents.portfolio.status import PickEvaluator, PortfolioEvaluator, HistoricalEvaluator

PORTFOLIO = "test"


def _make_portfolio(tickers: list[tuple[str, float]], date: str = "2024-01-01") -> Portfolio:
    """Create a portfolio with entry_price set for tests."""
    return Portfolio(
        date=date,
        picks=[
            Pick(ticker=t, score=score, signal="BUY", decision_text=f"Buy {t}", entry_price=100.0)
            for t, score in tickers
        ],
    )


def _seed_period(tmp_path, date: str, period_return: float | None) -> None:
    """Archive a rebalance event for TWR tests."""
    picks = [Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="x", entry_price=150.0)]
    new_portfolio = Portfolio(date=date, picks=picks)
    event = RebalanceEvent(
        date=date,
        entries=[RebalanceEntry(pick=picks[0], action=RebalanceAction.HOLD, old_score=1.0, new_score=1.0)],
        period_return=period_return,
    )
    archive_rebalance(event, new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)


# ---------------------------------------------------------------------------
# PickEvaluator
# ---------------------------------------------------------------------------

class TestPickEvaluator:
    def test_returns_current_price_and_pct_change(self):
        pick = Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0)
        evaluator = PickEvaluator(price_fetcher=lambda t, d: 120.0)
        result = evaluator.evaluate(pick)
        assert result is not None
        current_price, pct_change = result
        assert current_price == 120.0
        assert abs(pct_change - 20.0) < 0.01

    def test_skips_pick_without_entry_price(self):
        pick = Pick(ticker="AAPL", signal="BUY", score=1.0)
        evaluator = PickEvaluator(price_fetcher=lambda t, d: 120.0)
        assert evaluator.evaluate(pick) is None

    def test_skips_pick_with_zero_entry_price(self):
        pick = Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=0.0)
        evaluator = PickEvaluator(price_fetcher=lambda t, d: 120.0)
        assert evaluator.evaluate(pick) is None

    def test_skips_pick_when_current_price_unavailable(self):
        pick = Pick(ticker="BAD", signal="BUY", score=1.0, entry_price=100.0)
        evaluator = PickEvaluator(price_fetcher=lambda t, d: None)
        assert evaluator.evaluate(pick) is None

    @pytest.mark.parametrize("entry,current,expected_pct", [
        (150.0, 165.0, 10.0),
        (100.0, 110.0, 10.0),
        (100.0, 80.0, -20.0),
    ])
    def test_pct_change_calculated_correctly(self, entry, current, expected_pct):
        pick = Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=entry)
        evaluator = PickEvaluator(price_fetcher=lambda t, d: current)
        result = evaluator.evaluate(pick)
        _, pct_change = result
        assert abs(pct_change - expected_pct) < 0.01


# ---------------------------------------------------------------------------
# PortfolioEvaluator
# ---------------------------------------------------------------------------

class TestPortfolioEvaluator:
    def test_evaluates_all_picks(self):
        portfolio = _make_portfolio([("AAPL", 1.0), ("MSFT", 0.5)])

        def fetch(ticker, date):
            return {"AAPL": 110.0, "MSFT": 120.0}.get(ticker, None)

        picks, _, _ = PortfolioEvaluator(price_fetcher=fetch).evaluate(portfolio)
        assert len(picks) == 2
        assert all(p.current_price is not None for p in picks)

    def test_avg_pct_calculated(self):
        portfolio = _make_portfolio([("AAPL", 1.0), ("MSFT", 1.0)])

        def fetch(ticker, date):
            return 110.0 if ticker == "AAPL" else 120.0

        _, portfolio_return, _ = PortfolioEvaluator(price_fetcher=fetch).evaluate(portfolio)
        assert abs(portfolio_return - 15.0) < 0.01

    def test_skips_unevaluable_picks(self):
        portfolio = _make_portfolio([("AAPL", 1.0), ("BAD", 1.0)])

        def fetch(ticker, date):
            return None if ticker == "BAD" else 110.0

        picks, _, _ = PortfolioEvaluator(price_fetcher=fetch).evaluate(portfolio)
        assert len(picks) == 1
        assert picks[0].ticker == "AAPL"

    def test_spy_benchmark(self):
        portfolio = _make_portfolio([("AAPL", 1.0)])

        def fetch(ticker, date):
            if ticker == "SPY":
                return 100.0 if date else 110.0
            return 110.0

        _, _, spy_return = PortfolioEvaluator(price_fetcher=fetch).evaluate(portfolio)
        assert spy_return == 10.0

    def test_spy_none_when_unavailable(self):
        portfolio = _make_portfolio([("AAPL", 1.0)])
        _, _, spy_return = PortfolioEvaluator(price_fetcher=lambda t, d: None if t == "SPY" else 110.0).evaluate(portfolio)
        assert spy_return is None

    def test_empty_portfolio(self):
        portfolio = Portfolio(date="2024-01-01", picks=[])
        picks, portfolio_return, _ = PortfolioEvaluator(price_fetcher=lambda t, d: 100.0).evaluate(portfolio)
        assert portfolio_return == 0.0
        assert picks == []


# ---------------------------------------------------------------------------
# HistoricalEvaluator
# ---------------------------------------------------------------------------

class TestHistoricalEvaluator:
    def test_returns_none_when_no_history(self):
        state = PortfolioState()
        assert HistoricalEvaluator.evaluate(state) is None

    def test_returns_none_when_all_period_returns_are_none(self, tmp_path):
        _seed_period(tmp_path, "2024-01-01", None)
        from tradingagents.portfolio.persistence import load_state
        state = load_state(str(tmp_path), PORTFOLIO)
        assert HistoricalEvaluator.evaluate(state) is None

    @pytest.mark.parametrize("returns,expected_twr", [
        ([0.10], 0.10),
        ([0.10, 0.10], 0.21),
        ([0.20, -0.10], 0.08),
        ([0.10, None], 0.10),
    ], ids=["single", "two_gains", "gain_loss", "skip_none"])
    def test_twr_calculation(self, tmp_path, returns, expected_twr):
        dates = [f"2024-0{i+1}-01" for i in range(len(returns))]
        for date, r in zip(dates, returns):
            _seed_period(tmp_path, date, r)
        from tradingagents.portfolio.persistence import load_state
        state = load_state(str(tmp_path), PORTFOLIO)
        assert abs(HistoricalEvaluator.evaluate(state) - expected_twr) < 0.0001

    def test_current_portfolio_only_no_snapshots(self):
        """First iteration: no rebalance yet, TWR derived from current_price as exit."""
        state = PortfolioState()
        live = Portfolio(date="2024-01-01", picks=[
            Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0, current_price=115.0),
        ])
        twr = HistoricalEvaluator.evaluate(state, current_portfolio=live)
        assert abs(twr - 0.15) < 0.0001

    def test_current_portfolio_with_snapshots(self, tmp_path):
        """Ongoing: snapshots from past rebalances + live current period."""
        _seed_period(tmp_path, "2024-01-01", 0.10)
        from tradingagents.portfolio.persistence import load_state
        state = load_state(str(tmp_path), PORTFOLIO)
        live = Portfolio(date="2024-02-01", picks=[
            Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0, current_price=105.0),
        ])
        # TWR = (1.10) * (1.05) - 1 = 0.155
        twr = HistoricalEvaluator.evaluate(state, current_portfolio=live)
        assert abs(twr - 0.155) < 0.0001

    def test_current_portfolio_none_unchanged_behavior(self):
        """current_portfolio=None has no effect — same as before."""
        state = PortfolioState()
        assert HistoricalEvaluator.evaluate(state, current_portfolio=None) is None

    def test_current_portfolio_no_prices_skipped(self):
        """Picks without current_price are ignored in period return."""
        state = PortfolioState()
        live = Portfolio(date="2024-01-01", picks=[
            Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0),
        ])
        assert HistoricalEvaluator.evaluate(state, current_portfolio=live) is None

    def test_snapshots_not_mutated(self, tmp_path):
        """Passing current_portfolio must not modify state.snapshots."""
        _seed_period(tmp_path, "2024-01-01", 0.10)
        from tradingagents.portfolio.persistence import load_state
        state = load_state(str(tmp_path), PORTFOLIO)
        original_len = len(state.past_portfolios)
        live = Portfolio(date="2024-02-01", picks=[
            Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0, current_price=105.0),
        ])
        HistoricalEvaluator.evaluate(state, current_portfolio=live)
        assert len(state.past_portfolios) == original_len


# ---------------------------------------------------------------------------
# Persist enriched status to state.json
# ---------------------------------------------------------------------------

class TestStatusPersistence:
    def test_save_portfolio_persists_enriched_picks(self, tmp_path):
        picks = [
            Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="x",
                 entry_date="2024-01-01", entry_price=150.0, current_price=165.0, pct_change=10.0),
        ]
        save_portfolio(picks, date="2024-01-01", output_dir=str(tmp_path), portfolio=PORTFOLIO)
        loaded = load_portfolio(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert loaded.picks[0].current_price == 165.0
        assert loaded.picks[0].pct_change == 10.0
        assert loaded.picks[0].entry_price == 150.0

    def test_save_portfolio_persists_aggregate_metrics(self, tmp_path):
        picks = [Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
        save_portfolio(
            picks, date="2024-01-01", output_dir=str(tmp_path), portfolio=PORTFOLIO,
            portfolio_return=5.5, spy_return=3.2, twr=0.08,
        )
        loaded = load_portfolio(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert loaded.portfolio_return == 5.5
        assert loaded.spy_return == 3.2
        assert loaded.twr == 0.08
