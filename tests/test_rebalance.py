"""Tests für Ticket 2: rebalance — Nach 30 Tagen: Verkaufen, Kaufen oder Halten."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.portfolio.batch_runner import PickResult
from tradingagents.portfolio.persistence import save_picks, load_picks
from tradingagents.portfolio.rebalancer import Rebalancer, RebalanceAction, RebalanceResult


def _make_pick(ticker: str, score: float, signal: str = "BUY") -> PickResult:
    return PickResult(ticker=ticker, score=score, signal=signal, decision_text=f"Decision for {ticker}")


def _make_pick_dict(ticker: str, score: float, signal: str = "BUY") -> dict:
    return {"ticker": ticker, "score": score, "signal": signal, "decision_text": f"Decision for {ticker}"}


# ---------------------------------------------------------------------------
# RebalanceAction enum
# ---------------------------------------------------------------------------

class TestRebalanceAction:
    def test_enum_values_exist(self):
        assert RebalanceAction.HOLD
        assert RebalanceAction.SELL
        assert RebalanceAction.BUY


# ---------------------------------------------------------------------------
# RebalanceResult dataclass
# ---------------------------------------------------------------------------

class TestRebalanceResult:
    def test_fields_present(self):
        r = RebalanceResult(
            ticker="AAPL",
            action=RebalanceAction.HOLD,
            old_score=1.0,
            new_score=1.0,
        )
        assert r.ticker == "AAPL"
        assert r.action == RebalanceAction.HOLD
        assert r.old_score == 1.0
        assert r.new_score == 1.0


# ---------------------------------------------------------------------------
# Rebalancer core logic
# ---------------------------------------------------------------------------

class TestRebalancer:
    """Tests für die Rebalancing-Logik."""

    def _make_rebalancer(self, min_improvement: float = 0.3):
        return Rebalancer(min_improvement=min_improvement)

    def test_hold_when_score_unchanged(self):
        # NVDA score 0.1, MSFT score 0.0 → diff 0.1 < min_improvement 0.3 → kein Tausch
        rb = self._make_rebalancer()
        old_picks = [_make_pick_dict("AAPL", 1.0), _make_pick_dict("MSFT", 0.0, "HOLD")]
        new_scores = {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 0.1}
        results = rb.compute(old_picks, new_scores, top_n=2)
        actions = {r.ticker: r.action for r in results}
        assert actions["AAPL"] == RebalanceAction.HOLD
        assert actions["MSFT"] == RebalanceAction.HOLD

    def test_sell_and_buy_when_improvement_exceeds_hurdle(self):
        rb = self._make_rebalancer(min_improvement=0.3)
        # MSFT (score 0.0) should be replaced by NVDA (score=1.0, diff=1.0 > 0.3)
        old_picks = [_make_pick_dict("AAPL", 1.0), _make_pick_dict("MSFT", 0.0, "HOLD")]
        new_scores = {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 1.0}
        results = rb.compute(old_picks, new_scores, top_n=2)
        actions = {r.ticker: r.action for r in results}
        assert actions["AAPL"] == RebalanceAction.HOLD
        assert actions["MSFT"] == RebalanceAction.SELL
        assert actions["NVDA"] == RebalanceAction.BUY

    def test_no_replace_when_improvement_below_hurdle(self):
        rb = self._make_rebalancer(min_improvement=0.5)
        # NVDA has score 0.2, MSFT has score 0.0 → diff 0.2 < 0.5, no swap
        old_picks = [_make_pick_dict("AAPL", 1.0), _make_pick_dict("MSFT", 0.0, "HOLD")]
        new_scores = {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 0.2}
        results = rb.compute(old_picks, new_scores, top_n=2)
        actions = {r.ticker: r.action for r in results}
        assert RebalanceAction.SELL not in actions.values()
        assert RebalanceAction.BUY not in actions.values()

    def test_result_always_has_exactly_top_n_final_tickers(self):
        rb = self._make_rebalancer()
        old_picks = [_make_pick_dict(t, 1.0) for t in ["AAPL", "MSFT", "GOOG", "AMZN", "META"]]
        # Add 5 new better candidates
        new_scores = {t: 1.0 for t in ["AAPL", "MSFT", "GOOG", "AMZN", "META"]}
        new_scores.update({"NVDA": 1.0, "TSLA": 1.0, "V": 1.0, "MA": 1.0, "JPM": 1.0})
        results = rb.compute(old_picks, new_scores, top_n=5)
        final_tickers = {r.ticker for r in results if r.action in (RebalanceAction.HOLD, RebalanceAction.BUY)}
        assert len(final_tickers) == 5

    def test_old_score_and_new_score_populated(self):
        rb = self._make_rebalancer()
        old_picks = [_make_pick_dict("AAPL", 0.5)]
        new_scores = {"AAPL": 1.0}
        results = rb.compute(old_picks, new_scores, top_n=1)
        r = results[0]
        assert r.ticker == "AAPL"
        assert r.old_score == 0.5
        assert r.new_score == 1.0


# ---------------------------------------------------------------------------
# Persistence: history archiving
# ---------------------------------------------------------------------------

class TestHistoryArchiving:
    def test_archive_creates_history_dir(self, tmp_path):
        from tradingagents.portfolio.persistence import archive_picks

        picks = [_make_pick("AAPL", 1.0)]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        history_dir = tmp_path / "history"
        assert history_dir.exists()

    def test_archive_saves_dated_file(self, tmp_path):
        from tradingagents.portfolio.persistence import archive_picks

        picks = [_make_pick("AAPL", 1.0)]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        assert (tmp_path / "history" / "2024-01-01.json").exists()

    def test_archive_does_not_delete_latest(self, tmp_path):
        from tradingagents.portfolio.persistence import archive_picks
        from tradingagents.portfolio.persistence import PICKS_FILENAME

        picks = [_make_pick("AAPL", 1.0)]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        assert (tmp_path / PICKS_FILENAME).exists()
