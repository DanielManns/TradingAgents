"""Tests für Ticket 3: status — Aktuellen Portfolio-Stand anzeigen."""

from __future__ import annotations

import pytest

from tradingagents.portfolio.batch_runner import PickResult
from tradingagents.portfolio.persistence import save_picks, archive_picks
from tradingagents.portfolio.status import PortfolioStatus, PortfolioEntry, compute_twr


def _make_picks_payload(tickers: list[tuple[str, float]]) -> dict:
    """Erstellt ein picks-Dict wie es load_picks() zurückgibt."""
    return {
        "date": "2024-01-01",
        "picks": [
            {"ticker": t, "score": score, "signal": "BUY", "decision_text": f"Buy {t}"}
            for t, score in tickers
        ],
    }


def _seed_period(tmp_path, date: str, period_return: float | None) -> None:
    """Speichert und archiviert einen einzelnen Pick für TWR-Tests."""
    picks = [PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
    save_picks(picks, date=date, output_dir=str(tmp_path))
    archive_picks(date=date, period_return=period_return, output_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# PortfolioEntry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("price_at_pick,current_price,pct_change", [
    (150.0, 165.0, 10.0),
    (100.0, 110.0, 10.0),
])
def test_portfolio_entry_fields(price_at_pick, current_price, pct_change):
    entry = PortfolioEntry(
        ticker="AAPL",
        signal="BUY",
        pick_date="2024-01-01",
        price_at_pick=price_at_pick,
        current_price=current_price,
        pct_change=pct_change,
    )
    assert entry.ticker == "AAPL"
    assert entry.pct_change == pct_change


# ---------------------------------------------------------------------------
# PortfolioStatus
# ---------------------------------------------------------------------------

class TestPortfolioStatus:
    def test_build_entries_from_picks(self):
        picks = _make_picks_payload([("AAPL", 1.0), ("MSFT", 0.0)])
        prices = {"AAPL": 165.0, "MSFT": 310.0}
        prices_at_pick = {"AAPL": 150.0, "MSFT": 300.0}

        def fetch(ticker, date=None):
            return prices_at_pick.get(ticker) if date else prices.get(ticker)

        entries = PortfolioStatus(price_fetcher=fetch).build(picks)
        assert len(entries) == 2
        assert all(isinstance(e, PortfolioEntry) for e in entries)

    def test_pct_change_calculated_correctly(self):
        picks = _make_picks_payload([("AAPL", 1.0)])

        entries = PortfolioStatus(price_fetcher=lambda t, date=None: 100.0 if date else 120.0).build(picks)
        assert abs(entries[0].pct_change - 20.0) < 0.01

    def test_portfolio_avg_pct_change(self):
        picks = _make_picks_payload([("AAPL", 1.0), ("MSFT", 1.0)])

        def fetch(ticker, date=None):
            if date:
                return 100.0
            return 110.0 if ticker == "AAPL" else 120.0

        ps = PortfolioStatus(price_fetcher=fetch)
        assert abs(ps.portfolio_avg_pct(ps.build(picks)) - 15.0) < 0.01

    def test_none_price_skipped_gracefully(self):
        picks = _make_picks_payload([("AAPL", 1.0), ("BADTICKER", 1.0)])

        def fetch(ticker, date=None):
            return None if ticker == "BADTICKER" else (110.0 if date else 121.0)

        tickers = [e.ticker for e in PortfolioStatus(price_fetcher=fetch).build(picks)]
        assert "BADTICKER" not in tickers
        assert "AAPL" in tickers

    def test_spy_benchmark(self):
        picks = _make_picks_payload([("AAPL", 1.0)])
        fetch = lambda t, date=None: 100.0 if date else 110.0
        ps = PortfolioStatus(price_fetcher=fetch)
        spy_pct = ps.spy_pct_change(pick_date=picks["date"], price_fetcher=fetch)
        assert isinstance(spy_pct, float | type(None))


# ---------------------------------------------------------------------------
# compute_twr
# ---------------------------------------------------------------------------

class TestComputeTWR:
    def test_returns_none_when_no_history(self, tmp_path):
        assert compute_twr(output_dir=str(tmp_path)) is None

    def test_returns_none_when_all_period_returns_are_none(self, tmp_path):
        _seed_period(tmp_path, "2024-01-01", None)
        assert compute_twr(output_dir=str(tmp_path)) is None

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
        assert abs(compute_twr(output_dir=str(tmp_path)) - expected_twr) < 0.0001
