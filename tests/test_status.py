"""Tests für Ticket 3: status — Aktuellen Portfolio-Stand anzeigen."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from tradingagents.portfolio.status import PortfolioStatus, PortfolioEntry


def _make_picks_payload(tickers_with_dates: list[tuple[str, str, float]]) -> dict:
    """Erstellt ein picks-Dict wie es load_picks() zurückgibt."""
    return {
        "date": "2024-01-01",
        "picks": [
            {"ticker": t, "score": score, "signal": "BUY", "decision_text": f"Buy {t}"}
            for t, _pick_date, score in tickers_with_dates
        ],
    }


class TestPortfolioEntry:
    def test_fields_present(self):
        entry = PortfolioEntry(
            ticker="AAPL",
            signal="BUY",
            pick_date="2024-01-01",
            price_at_pick=150.0,
            current_price=165.0,
            pct_change=10.0,
        )
        assert entry.ticker == "AAPL"
        assert entry.pct_change == 10.0

    def test_pct_change_positive_when_price_increased(self):
        entry = PortfolioEntry(
            ticker="AAPL",
            signal="BUY",
            pick_date="2024-01-01",
            price_at_pick=100.0,
            current_price=110.0,
            pct_change=10.0,
        )
        assert entry.pct_change > 0


class TestPortfolioStatus:
    def _mock_price_fetcher(self, prices: dict[str, float]):
        """Erstellt eine Mock-Preisfunktion."""
        def fetch(ticker: str, date: str | None = None) -> float | None:
            return prices.get(ticker)
        return fetch

    def test_build_entries_from_picks(self):
        picks = _make_picks_payload([("AAPL", "2024-01-01", 1.0), ("MSFT", "2024-01-01", 0.0)])
        prices = {"AAPL": 165.0, "MSFT": 310.0}
        prices_at_pick = {"AAPL": 150.0, "MSFT": 300.0}

        def fetch(ticker: str, date: str | None = None) -> float | None:
            if date:
                return prices_at_pick.get(ticker)
            return prices.get(ticker)

        ps = PortfolioStatus(price_fetcher=fetch)
        entries = ps.build(picks)
        assert len(entries) == 2
        assert all(isinstance(e, PortfolioEntry) for e in entries)

    def test_pct_change_calculated_correctly(self):
        picks = _make_picks_payload([("AAPL", "2024-01-01", 1.0)])

        def fetch(ticker: str, date: str | None = None) -> float | None:
            if date:
                return 100.0
            return 120.0

        ps = PortfolioStatus(price_fetcher=fetch)
        entries = ps.build(picks)
        assert abs(entries[0].pct_change - 20.0) < 0.01

    def test_portfolio_avg_pct_change(self):
        picks = _make_picks_payload([
            ("AAPL", "2024-01-01", 1.0),
            ("MSFT", "2024-01-01", 1.0),
        ])

        call_count = {"n": 0}

        def fetch(ticker: str, date: str | None = None) -> float | None:
            if date:
                return 100.0
            # AAPL → +10%, MSFT → +20%
            return 110.0 if ticker == "AAPL" else 120.0

        ps = PortfolioStatus(price_fetcher=fetch)
        entries = ps.build(picks)
        avg = ps.portfolio_avg_pct(entries)
        assert abs(avg - 15.0) < 0.01

    def test_none_price_skipped_gracefully(self):
        picks = _make_picks_payload([("AAPL", "2024-01-01", 1.0), ("BADTICKER", "2024-01-01", 1.0)])

        def fetch(ticker: str, date: str | None = None) -> float | None:
            if ticker == "BADTICKER":
                return None
            return 110.0 if date else 121.0

        ps = PortfolioStatus(price_fetcher=fetch)
        entries = ps.build(picks)
        tickers = [e.ticker for e in entries]
        assert "BADTICKER" not in tickers
        assert "AAPL" in tickers

    def test_spy_benchmark_included(self):
        picks = _make_picks_payload([("AAPL", "2024-01-01", 1.0)])

        def fetch(ticker: str, date: str | None = None) -> float | None:
            return 100.0 if date else 110.0

        ps = PortfolioStatus(price_fetcher=fetch)
        entries = ps.build(picks)
        spy_pct = ps.spy_pct_change(pick_date=picks["date"], price_fetcher=fetch)
        assert isinstance(spy_pct, float | type(None))
