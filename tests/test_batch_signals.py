"""Tests for save_batch_signals / load_batch_signals round-trip."""

from __future__ import annotations

from datetime import date

import pytest

from tradingagents.portfolio.models import Pick
from tradingagents.portfolio.persistence import load_batch_signals, save_batch_signals


@pytest.fixture
def sample_results() -> dict[date, list[Pick]]:
    return {
        date(2026, 3, 20): [
            Pick(ticker="AAPL", signal="BUY", score=0.9, decision_text="Strong buy"),
            Pick(ticker="MSFT", signal="HOLD", score=0.5, decision_text="Neutral"),
        ],
        date(2026, 3, 21): [
            Pick(ticker="AAPL", signal="SELL", score=0.2, decision_text="Weak outlook"),
        ],
    }


def test_round_trip(tmp_path, sample_results):
    out = str(tmp_path)
    save_batch_signals(sample_results, output_dir=out, portfolio="test")
    rows = load_batch_signals(output_dir=out, portfolio="test")

    assert len(rows) == 3
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"AAPL", "MSFT"}

    aapl_mar21 = next(r for r in rows if r["ticker"] == "AAPL" and r["date"] == "2026-03-21")
    assert aapl_mar21["signal"] == "SELL"
    assert aapl_mar21["score"] == 0.2


def test_dedup_on_resave(tmp_path, sample_results):
    """Re-saving with updated signals for same (ticker, date) should replace, not duplicate."""
    out = str(tmp_path)
    save_batch_signals(sample_results, output_dir=out, portfolio="test")

    updated = {
        date(2026, 3, 20): [
            Pick(ticker="AAPL", signal="STRONG_BUY", score=1.0, decision_text="Upgraded"),
        ],
    }
    save_batch_signals(updated, output_dir=out, portfolio="test")
    rows = load_batch_signals(output_dir=out, portfolio="test")

    aapl_rows = [r for r in rows if r["ticker"] == "AAPL" and r["date"] == "2026-03-20"]
    assert len(aapl_rows) == 1
    assert aapl_rows[0]["signal"] == "STRONG_BUY"
    assert len(rows) == 3  # AAPL 3/20 replaced, MSFT 3/20 + AAPL 3/21 still there


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_batch_signals(output_dir=str(tmp_path), portfolio="nonexistent")


def test_append_new_date(tmp_path, sample_results):
    """Saving signals for a new date should add to existing data."""
    out = str(tmp_path)
    save_batch_signals(sample_results, output_dir=out, portfolio="test")

    new_day = {
        date(2026, 3, 22): [
            Pick(ticker="GOOG", signal="BUY", score=0.8, decision_text="New pick"),
        ],
    }
    save_batch_signals(new_day, output_dir=out, portfolio="test")
    rows = load_batch_signals(output_dir=out, portfolio="test")

    assert len(rows) == 4
    assert any(r["ticker"] == "GOOG" and r["date"] == "2026-03-22" for r in rows)
