"""Tests for Ticket 1: pick command — Top-10 Aktien auswählen."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from tradingagents.portfolio.universe import UNIVERSE
from tradingagents.portfolio.scorer import KeywordScorer
from tradingagents.portfolio.batch_runner import BatchRunner, PickResult
from tradingagents.portfolio.persistence import save_picks, load_picks, PICKS_FILENAME


# ---------------------------------------------------------------------------
# Universe tests
# ---------------------------------------------------------------------------

class TestUniverse:
    def test_universe_is_list(self):
        assert isinstance(UNIVERSE, list)

    def test_universe_size(self):
        assert 25 <= len(UNIVERSE) <= 50

    def test_universe_entries_are_strings(self):
        for ticker in UNIVERSE:
            assert isinstance(ticker, str), f"{ticker!r} should be a string"

    def test_universe_entries_are_uppercase(self):
        for ticker in UNIVERSE:
            assert ticker == ticker.upper(), f"{ticker!r} should be uppercase"

    def test_universe_has_no_duplicates(self):
        assert len(UNIVERSE) == len(set(UNIVERSE))


# ---------------------------------------------------------------------------
# Scorer tests
# ---------------------------------------------------------------------------

class TestKeywordScorer:
    def setup_method(self):
        self.scorer = KeywordScorer()

    def test_buy_signal_scores_one(self):
        assert self.scorer.score("BUY") == 1.0

    def test_sell_signal_scores_minus_one(self):
        assert self.scorer.score("SELL") == -1.0

    def test_hold_signal_scores_zero(self):
        assert self.scorer.score("HOLD") == 0.0

    def test_case_insensitive_buy(self):
        assert self.scorer.score("buy") == 1.0

    def test_case_insensitive_sell(self):
        assert self.scorer.score("sell") == -1.0

    def test_case_insensitive_hold(self):
        assert self.scorer.score("hold") == 0.0

    def test_unknown_signal_scores_zero(self):
        assert self.scorer.score("UNKNOWN") == 0.0

    def test_whitespace_handling(self):
        assert self.scorer.score("  BUY  ") == 1.0


# ---------------------------------------------------------------------------
# BatchRunner tests
# ---------------------------------------------------------------------------

class TestBatchRunner:
    def _make_propagate_fn(self, signal_map: dict):
        """Creates a mock propagate_fn from a ticker→signal mapping."""
        def propagate_fn(ticker: str, date: str):
            signal = signal_map.get(ticker, "HOLD")
            final_state = {"final_trade_decision": f"Decision: {signal}"}
            return final_state, signal
        return propagate_fn

    def test_run_returns_pick_results(self):
        fn = self._make_propagate_fn({"AAPL": "BUY", "MSFT": "HOLD", "TSLA": "SELL"})
        runner = BatchRunner(propagate_fn=fn)
        results = runner.run(["AAPL", "MSFT", "TSLA"], "2024-01-01")
        assert len(results) == 3
        assert all(isinstance(r, PickResult) for r in results)

    def test_results_sorted_by_score_descending(self):
        fn = self._make_propagate_fn({"AAPL": "BUY", "MSFT": "HOLD", "TSLA": "SELL"})
        runner = BatchRunner(propagate_fn=fn)
        results = runner.run(["AAPL", "MSFT", "TSLA"], "2024-01-01")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_tiebreak_is_alphabetical(self):
        fn = self._make_propagate_fn({"GOOG": "BUY", "AAPL": "BUY"})
        runner = BatchRunner(propagate_fn=fn)
        results = runner.run(["GOOG", "AAPL"], "2024-01-01")
        assert results[0].ticker == "AAPL"
        assert results[1].ticker == "GOOG"

    def test_error_in_propagate_is_skipped(self):
        call_count = 0

        def failing_fn(ticker: str, date: str):
            nonlocal call_count
            call_count += 1
            if ticker == "BADTICKER":
                raise ValueError("Simulated failure")
            return {"final_trade_decision": "BUY"}, "BUY"

        runner = BatchRunner(propagate_fn=failing_fn)
        results = runner.run(["AAPL", "BADTICKER", "MSFT"], "2024-01-01")
        assert len(results) == 2
        tickers = [r.ticker for r in results]
        assert "BADTICKER" not in tickers
        assert call_count == 3

    def test_pick_result_contains_required_fields(self):
        fn = self._make_propagate_fn({"AAPL": "BUY"})
        runner = BatchRunner(propagate_fn=fn)
        results = runner.run(["AAPL"], "2024-01-01")
        r = results[0]
        assert r.ticker == "AAPL"
        assert r.score == 1.0
        assert r.signal == "BUY"
        assert isinstance(r.decision_text, str)

    def test_custom_scorer_is_used(self):
        custom_scorer = MagicMock()
        custom_scorer.score.return_value = 0.5
        fn = self._make_propagate_fn({"AAPL": "BUY"})
        runner = BatchRunner(propagate_fn=fn, scorer=custom_scorer)
        runner.run(["AAPL"], "2024-01-01")
        custom_scorer.score.assert_called_once_with("BUY")


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        picks = [
            PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="Strong buy"),
            PickResult(ticker="MSFT", score=0.0, signal="HOLD", decision_text="Hold steady"),
        ]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        loaded = load_picks(output_dir=str(tmp_path))
        assert loaded is not None
        assert len(loaded["picks"]) == 2
        assert loaded["picks"][0]["ticker"] == "AAPL"
        assert loaded["picks"][0]["score"] == 1.0

    def test_save_creates_json_file(self, tmp_path):
        picks = [PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        assert (tmp_path / PICKS_FILENAME).exists()

    def test_load_returns_none_when_no_file(self, tmp_path):
        result = load_picks(output_dir=str(tmp_path))
        assert result is None

    def test_saved_file_contains_date(self, tmp_path):
        picks = [PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        loaded = load_picks(output_dir=str(tmp_path))
        assert loaded["date"] == "2024-01-01"
