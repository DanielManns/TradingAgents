"""Tests für Ticket 4: Analyse-Caching — Batch-Lauf bezahlbar machen."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradingagents.portfolio.cache import AnalysisCache


class TestAnalysisCache:
    def test_cache_miss_returns_none(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path))
        assert cache.get("AAPL", "2024-01-01") is None

    def test_cache_hit_after_put(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path))
        payload = {"final_trade_decision": "BUY strongly"}
        cache.put("AAPL", "2024-01-01", payload, signal="BUY")
        result = cache.get("AAPL", "2024-01-01")
        assert result is not None
        assert result["signal"] == "BUY"
        assert result["final_state"]["final_trade_decision"] == "BUY strongly"

    def test_cache_creates_file_on_disk(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path))
        cache.put("AAPL", "2024-01-01", {}, signal="BUY")
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_different_tickers_are_separate_entries(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path))
        cache.put("AAPL", "2024-01-01", {"x": 1}, signal="BUY")
        cache.put("MSFT", "2024-01-01", {"x": 2}, signal="HOLD")
        assert cache.get("AAPL", "2024-01-01")["signal"] == "BUY"
        assert cache.get("MSFT", "2024-01-01")["signal"] == "HOLD"

    def test_different_dates_are_separate_entries(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path))
        cache.put("AAPL", "2024-01-01", {"x": 1}, signal="BUY")
        cache.put("AAPL", "2024-01-08", {"x": 2}, signal="SELL")
        assert cache.get("AAPL", "2024-01-01")["signal"] == "BUY"
        assert cache.get("AAPL", "2024-01-08")["signal"] == "SELL"

    def test_expired_entry_returns_none(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path), ttl_days=0)
        cache.put("AAPL", "2024-01-01", {}, signal="BUY")
        # ttl_days=0 → sofort abgelaufen
        assert cache.get("AAPL", "2024-01-01") is None

    def test_valid_entry_within_ttl_is_returned(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path), ttl_days=7)
        cache.put("AAPL", "2024-01-01", {}, signal="BUY")
        assert cache.get("AAPL", "2024-01-01") is not None

    def test_cache_key_uses_ticker_and_date(self, tmp_path):
        cache = AnalysisCache(cache_dir=str(tmp_path))
        key1 = cache._key("AAPL", "2024-01-01")
        key2 = cache._key("AAPL", "2024-01-02")
        key3 = cache._key("MSFT", "2024-01-01")
        assert key1 != key2
        assert key1 != key3


class TestBatchRunnerWithCache:
    """Integration-Test: BatchRunner nutzt Cache für bereits analysierte Ticker."""

    def test_cached_ticker_skips_propagate(self, tmp_path):
        from tradingagents.portfolio.batch_runner import BatchRunner
        from tradingagents.portfolio.cache import AnalysisCache

        call_log: list[str] = []

        def propagate_fn(ticker: str, date: str):
            call_log.append(ticker)
            return {"final_trade_decision": f"{ticker} BUY"}, "BUY"

        cache = AnalysisCache(cache_dir=str(tmp_path), ttl_days=7)
        # AAPL vorab in Cache legen
        cache.put("AAPL", "2024-01-01", {"final_trade_decision": "AAPL BUY cached"}, signal="BUY")

        runner = BatchRunner(propagate_fn=propagate_fn, cache=cache)
        results = runner.run(["AAPL", "MSFT"], "2024-01-01")

        # propagate_fn sollte nur für MSFT aufgerufen werden, nicht für AAPL
        assert "AAPL" not in call_log
        assert "MSFT" in call_log
        assert len(results) == 2

    def test_cache_miss_calls_propagate_and_stores(self, tmp_path):
        from tradingagents.portfolio.batch_runner import BatchRunner
        from tradingagents.portfolio.cache import AnalysisCache

        call_log: list[str] = []

        def propagate_fn(ticker: str, date: str):
            call_log.append(ticker)
            return {"final_trade_decision": f"{ticker} BUY"}, "BUY"

        cache = AnalysisCache(cache_dir=str(tmp_path), ttl_days=7)
        runner = BatchRunner(propagate_fn=propagate_fn, cache=cache)
        runner.run(["AAPL"], "2024-01-01")

        assert "AAPL" in call_log
        # Nach dem Lauf sollte AAPL im Cache sein
        assert cache.get("AAPL", "2024-01-01") is not None
