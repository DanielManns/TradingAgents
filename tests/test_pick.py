"""Tests for Ticket 1: pick command — Top-10 Aktien auswählen."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from tradingagents.portfolio.scorer import KeywordScorer
from tradingagents.portfolio.batch_runner import BatchRunner, PickResult
from tradingagents.portfolio.persistence import save_picks, load_picks, PICKS_FILENAME


# ---------------------------------------------------------------------------
# Scorer tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("signal,expected", [
    ("BUY", 1.0),
    ("buy", 1.0),
    ("  BUY  ", 1.0),
    ("SELL", -1.0),
    ("sell", -1.0),
    ("HOLD", 0.0),
    ("hold", 0.0),
    ("UNKNOWN", 0.0),
    ("", 0.0),
])
def test_keyword_scorer(signal: str, expected: float):
    assert KeywordScorer().score(signal) == expected


@pytest.mark.parametrize("signal", ["BUYBACK", "RESELL"])
def test_keyword_scorer_no_substring_false_positives(signal: str):
    """Word-boundary matching verhindert false positives bei Substrings."""
    score = KeywordScorer().score(signal)
    # "BUYBACK" darf nicht als BUY gewertet werden, "RESELL" nicht als SELL
    assert score == 0.0


# ---------------------------------------------------------------------------
# BatchRunner tests
# ---------------------------------------------------------------------------

class TestBatchRunner:
    def _make_propagate_fn(self, signal_map: dict):
        def propagate_fn(ticker: str, date: str):
            signal = signal_map.get(ticker, "HOLD")
            return {"final_trade_decision": f"Decision: {signal}"}, signal
        return propagate_fn

    def test_run_returns_correct_number_of_results(self):
        fn = self._make_propagate_fn({"AAPL": "BUY", "MSFT": "HOLD", "TSLA": "SELL"})
        results = BatchRunner(propagate_fn=fn).run(["AAPL", "MSFT", "TSLA"], "2024-01-01")
        assert len(results) == 3

    def test_all_results_are_pick_result_instances(self):
        fn = self._make_propagate_fn({"AAPL": "BUY"})
        results = BatchRunner(propagate_fn=fn).run(["AAPL"], "2024-01-01")
        assert all(isinstance(r, PickResult) for r in results)

    def test_results_sorted_descending_by_score(self):
        fn = self._make_propagate_fn({"AAPL": "BUY", "MSFT": "HOLD", "TSLA": "SELL"})
        results = BatchRunner(propagate_fn=fn).run(["TSLA", "MSFT", "AAPL"], "2024-01-01")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_tiebreak_is_alphabetical(self):
        fn = self._make_propagate_fn({"GOOG": "BUY", "AAPL": "BUY", "MSFT": "BUY"})
        results = BatchRunner(propagate_fn=fn).run(["GOOG", "MSFT", "AAPL"], "2024-01-01")
        tickers = [r.ticker for r in results]
        assert tickers == sorted(tickers)

    def test_failing_ticker_is_skipped(self):
        def failing_fn(ticker: str, date: str):
            if ticker == "BAD":
                raise RuntimeError("Simulated failure")
            return {"final_trade_decision": "BUY"}, "BUY"

        results = BatchRunner(propagate_fn=failing_fn).run(["AAPL", "BAD", "MSFT"], "2024-01-01")
        tickers = [r.ticker for r in results]
        assert "BAD" not in tickers
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_all_tickers_attempted_despite_failures(self):
        calls: list[str] = []

        def tracking_fn(ticker: str, date: str):
            calls.append(ticker)
            if ticker == "BAD":
                raise RuntimeError("fail")
            return {"final_trade_decision": "BUY"}, "BUY"

        BatchRunner(propagate_fn=tracking_fn).run(["AAPL", "BAD", "MSFT"], "2024-01-01")
        assert calls == ["AAPL", "BAD", "MSFT"]

    def test_score_is_derived_from_signal(self):
        fn = self._make_propagate_fn({"AAPL": "BUY", "MSFT": "SELL", "GOOG": "HOLD"})
        results = {r.ticker: r for r in BatchRunner(propagate_fn=fn).run(["AAPL", "MSFT", "GOOG"], "2024-01-01")}
        assert results["AAPL"].score == 1.0
        assert results["MSFT"].score == -1.0
        assert results["GOOG"].score == 0.0

    def test_decision_text_stored_from_final_state(self):
        def fn(ticker: str, date: str):
            return {"final_trade_decision": f"Detailed analysis for {ticker}"}, "BUY"

        results = BatchRunner(propagate_fn=fn).run(["AAPL"], "2024-01-01")
        assert results[0].decision_text == "Detailed analysis for AAPL"

    def test_custom_scorer_called_with_signal(self):
        custom_scorer = MagicMock()
        custom_scorer.score.return_value = 0.5
        fn = self._make_propagate_fn({"AAPL": "BUY"})
        BatchRunner(propagate_fn=fn, scorer=custom_scorer).run(["AAPL"], "2024-01-01")
        custom_scorer.score.assert_called_once_with("BUY")

    def test_custom_scorer_score_used_in_result(self):
        custom_scorer = MagicMock()
        custom_scorer.score.return_value = 0.75
        fn = self._make_propagate_fn({"AAPL": "BUY"})
        results = BatchRunner(propagate_fn=fn, scorer=custom_scorer).run(["AAPL"], "2024-01-01")
        assert results[0].score == 0.75

    def test_empty_ticker_list_returns_empty(self):
        fn = self._make_propagate_fn({})
        results = BatchRunner(propagate_fn=fn).run([], "2024-01-01")
        assert results == []

    def test_majority_failures_raises_runtime_error(self):
        def always_fail(ticker: str, date: str):
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="Analysen fehlgeschlagen"):
            BatchRunner(propagate_fn=always_fail).run(["AAPL", "MSFT"], "2024-01-01")


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
        assert load_picks(output_dir=str(tmp_path)) is None

    def test_saved_file_contains_date(self, tmp_path):
        picks = [PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        assert load_picks(output_dir=str(tmp_path))["date"] == "2024-01-01"

    def test_all_fields_preserved(self, tmp_path):
        picks = [PickResult(ticker="NVDA", score=-1.0, signal="SELL", decision_text="Bearish outlook")]
        save_picks(picks, date="2024-06-15", output_dir=str(tmp_path))
        loaded = load_picks(output_dir=str(tmp_path))["picks"][0]
        assert loaded["ticker"] == "NVDA"
        assert loaded["score"] == -1.0
        assert loaded["signal"] == "SELL"
        assert loaded["decision_text"] == "Bearish outlook"

    def test_save_overwrites_previous_file(self, tmp_path):
        save_picks([PickResult("AAPL", 1.0, "BUY", "x")], date="2024-01-01", output_dir=str(tmp_path))
        save_picks([PickResult("MSFT", 0.0, "HOLD", "y")], date="2024-01-08", output_dir=str(tmp_path))
        loaded = load_picks(output_dir=str(tmp_path))
        assert len(loaded["picks"]) == 1
        assert loaded["picks"][0]["ticker"] == "MSFT"

    def test_entry_price_stored_and_loaded(self, tmp_path):
        picks = [PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="x", entry_price=213.49)]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        loaded = load_picks(output_dir=str(tmp_path))["picks"][0]
        assert loaded["entry_price"] == 213.49

    def test_entry_price_none_when_not_provided(self, tmp_path):
        picks = [PickResult(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
        save_picks(picks, date="2024-01-01", output_dir=str(tmp_path))
        loaded = load_picks(output_dir=str(tmp_path))["picks"][0]
        assert loaded["entry_price"] is None
