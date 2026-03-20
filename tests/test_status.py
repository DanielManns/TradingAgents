"""Tests for Ticket 3: status — display current portfolio state."""

from __future__ import annotations

import pytest

from tradingagents.portfolio.models import Pick, Portfolio, PortfolioState, RebalanceAction, RebalanceEntry, RebalanceEvent
from tradingagents.portfolio.persistence import save_portfolio, load_portfolio, archive_rebalance
from tradingagents.portfolio.status import PortfolioStatus, compute_twr

PORTFOLIO = "test"


def _make_portfolio(tickers: list[tuple[str, float]], date: str = "2024-01-01") -> Portfolio:
    """Create a portfolio for tests."""
    return Portfolio(
        date=date,
        picks=[
            Pick(ticker=t, score=score, signal="BUY", decision_text=f"Buy {t}")
            for t, score in tickers
        ],
    )


def _seed_period(tmp_path, date: str, period_return: float | None) -> None:
    """Archive a rebalance event for TWR tests."""
    picks = [Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
    new_portfolio = Portfolio(date=date, picks=picks)
    event = RebalanceEvent(
        date=date,
        entries=[RebalanceEntry(pick=picks[0], action=RebalanceAction.HOLD, old_score=1.0, new_score=1.0)],
        period_return=period_return,
    )
    archive_rebalance(event, new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)


# ---------------------------------------------------------------------------
# Pick as status entry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry_price,current_price,pct_change", [
    (150.0, 165.0, 10.0),
    (100.0, 110.0, 10.0),
])
def test_pick_status_fields(entry_price, current_price, pct_change):
    pick = Pick(
        ticker="AAPL",
        signal="BUY",
        entry_date="2024-01-01",
        entry_price=entry_price,
        current_price=current_price,
        pct_change=pct_change,
    )
    assert pick.ticker == "AAPL"
    assert pick.pct_change == pct_change


# ---------------------------------------------------------------------------
# PortfolioStatus
# ---------------------------------------------------------------------------

class TestPortfolioStatus:
    def test_build_entries_from_portfolio(self):
        portfolio = _make_portfolio([("AAPL", 1.0), ("MSFT", 0.0)])
        prices = {"AAPL": 165.0, "MSFT": 310.0}
        prices_at_pick = {"AAPL": 150.0, "MSFT": 300.0}

        def fetch(ticker, date):
            return prices_at_pick.get(ticker) if date else prices.get(ticker)

        entries = PortfolioStatus(price_fetcher=fetch).build(portfolio)
        assert len(entries) == 2
        assert all(isinstance(e, Pick) for e in entries)

    def test_pct_change_calculated_correctly(self):
        portfolio = _make_portfolio([("AAPL", 1.0)])

        entries = PortfolioStatus(price_fetcher=lambda t, date: 100.0 if date else 120.0).build(portfolio)
        assert abs(entries[0].pct_change - 20.0) < 0.01

    def test_portfolio_avg_pct_change(self):
        portfolio = _make_portfolio([("AAPL", 1.0), ("MSFT", 1.0)])

        def fetch(ticker, date):
            if date:
                return 100.0
            return 110.0 if ticker == "AAPL" else 120.0

        ps = PortfolioStatus(price_fetcher=fetch)
        assert abs(ps.portfolio_avg_pct(ps.build(portfolio)) - 15.0) < 0.01

    def test_none_price_skipped_gracefully(self):
        portfolio = _make_portfolio([("AAPL", 1.0), ("BADTICKER", 1.0)])

        def fetch(ticker, date):
            return None if ticker == "BADTICKER" else (110.0 if date else 121.0)

        tickers = [e.ticker for e in PortfolioStatus(price_fetcher=fetch).build(portfolio)]
        assert "BADTICKER" not in tickers
        assert "AAPL" in tickers

    def test_spy_benchmark(self):
        portfolio = _make_portfolio([("AAPL", 1.0)])
        fetch = lambda t, date: 100.0 if date else 110.0
        ps = PortfolioStatus(price_fetcher=fetch)
        spy_pct = ps.spy_pct_change(pick_date=portfolio.date)
        assert isinstance(spy_pct, float | type(None))


# ---------------------------------------------------------------------------
# compute_twr
# ---------------------------------------------------------------------------

class TestComputeTWR:
    def test_returns_none_when_no_history(self, tmp_path):
        assert compute_twr(output_dir=str(tmp_path), portfolio=PORTFOLIO) is None

    def test_returns_none_when_all_period_returns_are_none(self, tmp_path):
        _seed_period(tmp_path, "2024-01-01", None)
        assert compute_twr(output_dir=str(tmp_path), portfolio=PORTFOLIO) is None

    @pytest.mark.parametrize("returns,expected_twr", [
        ([0.10], 0.10),                    # single period
        ([0.10, 0.10], 0.21),              # two equal periods: 1.1*1.1 - 1
        ([0.20, -0.10], 0.08),             # gain then loss: 1.2*0.9 - 1
        ([0.10, None], 0.10),              # None period skipped
    ], ids=["single", "two_gains", "gain_loss", "skip_none"])
    def test_twr_calculation(self, tmp_path, returns, expected_twr):
        dates = [f"2024-0{i+1}-01" for i in range(len(returns))]
        for date, r in zip(dates, returns):
            _seed_period(tmp_path, date, r)
        assert abs(compute_twr(output_dir=str(tmp_path), portfolio=PORTFOLIO) - expected_twr) < 0.0001


# ---------------------------------------------------------------------------
# Persist enriched status to current.json
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
