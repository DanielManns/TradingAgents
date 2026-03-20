"""Tests for evaluation: pick, portfolio, and historical performance."""

from __future__ import annotations

import pytest

from tradingagents.portfolio.models import Pick, Portfolio, PortfolioState, RebalanceAction, RebalanceEntry, RebalanceEvent
from tradingagents.portfolio.persistence import save_portfolio, load_portfolio, archive_rebalance
from tradingagents.portfolio.evaluate import evaluate_pick, evaluate_picks, evaluate_portfolio, evaluate_portfolio_state, live_period_return

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
# evaluate_pick
# ---------------------------------------------------------------------------

def test_pick_returns_current_price_and_pct_change():
    pick = Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0)
    result = evaluate_pick(pick, price_fetcher=lambda t, d: 120.0)
    assert result is not None
    current_price, pct_change = result
    assert current_price == 120.0
    assert abs(pct_change - 20.0) < 0.01

def test_pick_skips_without_entry_price():
    pick = Pick(ticker="AAPL", signal="BUY", score=1.0)
    assert evaluate_pick(pick, price_fetcher=lambda t, d: 120.0) is None

def test_pick_skips_with_zero_entry_price():
    pick = Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=0.0)
    assert evaluate_pick(pick, price_fetcher=lambda t, d: 120.0) is None

def test_pick_skips_when_current_price_unavailable():
    pick = Pick(ticker="BAD", signal="BUY", score=1.0, entry_price=100.0)
    assert evaluate_pick(pick, price_fetcher=lambda t, d: None) is None

@pytest.mark.parametrize("entry,current,expected_pct", [
    (150.0, 165.0, 10.0),
    (100.0, 110.0, 10.0),
    (100.0, 80.0, -20.0),
])
def test_pick_pct_change_calculated_correctly(entry, current, expected_pct):
    pick = Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=entry)
    result = evaluate_pick(pick, price_fetcher=lambda t, d: current)
    _, pct_change = result
    assert abs(pct_change - expected_pct) < 0.01


# ---------------------------------------------------------------------------
# evaluate_picks
# ---------------------------------------------------------------------------

def test_picks_evaluates_all():
    portfolio = _make_portfolio([("AAPL", 1.0), ("MSFT", 0.5)])

    def fetch(ticker, date):
        return {"AAPL": 110.0, "MSFT": 120.0}.get(ticker, None)

    results = evaluate_picks(portfolio.picks, price_fetcher=fetch)
    assert len(results) == 2
    assert "AAPL" in results and "MSFT" in results
    assert results["AAPL"] == (110.0, 10.0)
    assert results["MSFT"] == (120.0, 20.0)

def test_picks_skips_unevaluable():
    portfolio = _make_portfolio([("AAPL", 1.0), ("BAD", 1.0)])

    def fetch(ticker, date):
        return None if ticker == "BAD" else 110.0

    results = evaluate_picks(portfolio.picks, price_fetcher=fetch)
    assert len(results) == 1
    assert "AAPL" in results

def test_picks_empty():
    results = evaluate_picks([], price_fetcher=lambda t, d: 100.0)
    assert results == {}


# ---------------------------------------------------------------------------
# evaluate_portfolio
# ---------------------------------------------------------------------------

def test_portfolio_avg_pct_calculated():
    # AAPL: 10%, MSFT: 20% → avg 15%
    portfolio_return, _ = evaluate_portfolio([10.0, 20.0], date="2024-01-01", price_fetcher=lambda t, d: 100.0)
    assert abs(portfolio_return - 15.0) < 0.01

def test_portfolio_spy_benchmark():
    def fetch(ticker, date):
        if ticker == "SPY":
            return 100.0 if date else 110.0
        return 110.0

    _, spy_return = evaluate_portfolio([10.0], date="2024-01-01", price_fetcher=fetch)
    assert spy_return == 10.0

def test_portfolio_spy_none_when_unavailable():
    _, spy_return = evaluate_portfolio([10.0], date="2024-01-01", price_fetcher=lambda t, d: None if t == "SPY" else 110.0)
    assert spy_return is None

def test_portfolio_empty():
    portfolio_return, _ = evaluate_portfolio([], date="2024-01-01", price_fetcher=lambda t, d: 100.0)
    assert portfolio_return == 0.0


# ---------------------------------------------------------------------------
# live_period_return
# ---------------------------------------------------------------------------

def test_live_period_return_computes_fractional():
    picks = [Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0)]
    eval_results = {"AAPL": (115.0, 15.0)}
    ret = live_period_return(picks, eval_results)
    assert abs(ret - 0.15) < 0.0001

def test_live_period_return_none_when_no_results():
    picks = [Pick(ticker="AAPL", signal="BUY", score=1.0, entry_price=100.0)]
    ret = live_period_return(picks, {})
    assert ret is None

def test_live_period_return_skips_missing_entry_price():
    picks = [Pick(ticker="AAPL", signal="BUY", score=1.0)]
    eval_results = {"AAPL": (115.0, 15.0)}
    ret = live_period_return(picks, eval_results)
    assert ret is None


# ---------------------------------------------------------------------------
# evaluate_portfolio_state
# ---------------------------------------------------------------------------

def test_history_returns_none_when_no_history():
    state = PortfolioState()
    assert evaluate_portfolio_state(state) is None

def test_history_returns_none_when_all_period_returns_are_none(tmp_path):
    _seed_period(tmp_path, "2024-01-01", None)
    from tradingagents.portfolio.persistence import load_state
    state = load_state(str(tmp_path), PORTFOLIO)
    assert evaluate_portfolio_state(state) is None

@pytest.mark.parametrize("returns,expected_twr", [
    ([0.10], 0.10),
    ([0.10, 0.10], 0.21),
    ([0.20, -0.10], 0.08),
    ([0.10, None], 0.10),
], ids=["single", "two_gains", "gain_loss", "skip_none"])
def test_history_twr_calculation(tmp_path, returns, expected_twr):
    dates = [f"2024-0{i+1}-01" for i in range(len(returns))]
    for date, r in zip(dates, returns):
        _seed_period(tmp_path, date, r)
    from tradingagents.portfolio.persistence import load_state
    state = load_state(str(tmp_path), PORTFOLIO)
    assert abs(evaluate_portfolio_state(state) - expected_twr) < 0.0001

def test_history_live_period_return_only():
    """First iteration: no rebalance yet, TWR derived from live_period_return."""
    state = PortfolioState()
    twr = evaluate_portfolio_state(state, live_period_return=0.15)
    assert abs(twr - 0.15) < 0.0001

def test_history_live_period_return_with_snapshots(tmp_path):
    """Ongoing: snapshots from past rebalances + live current period."""
    _seed_period(tmp_path, "2024-01-01", 0.10)
    from tradingagents.portfolio.persistence import load_state
    state = load_state(str(tmp_path), PORTFOLIO)
    # TWR = (1.10) * (1.05) - 1 = 0.155
    twr = evaluate_portfolio_state(state, live_period_return=0.05)
    assert abs(twr - 0.155) < 0.0001

def test_history_no_live_return_unchanged():
    state = PortfolioState()
    assert evaluate_portfolio_state(state, live_period_return=None) is None

def test_history_snapshots_not_mutated(tmp_path):
    _seed_period(tmp_path, "2024-01-01", 0.10)
    from tradingagents.portfolio.persistence import load_state
    state = load_state(str(tmp_path), PORTFOLIO)
    original_len = len(state.past_portfolios)
    evaluate_portfolio_state(state, live_period_return=0.05)
    assert len(state.past_portfolios) == original_len


# ---------------------------------------------------------------------------
# Persist enriched status to state.json
# ---------------------------------------------------------------------------

def test_save_portfolio_persists_enriched_picks(tmp_path):
    picks = [
        Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="x",
             entry_date="2024-01-01", entry_price=150.0, current_price=165.0, pct_change=10.0),
    ]
    save_portfolio(picks, date="2024-01-01", output_dir=str(tmp_path), portfolio=PORTFOLIO)
    loaded = load_portfolio(output_dir=str(tmp_path), portfolio=PORTFOLIO)
    assert loaded.picks[0].current_price == 165.0
    assert loaded.picks[0].pct_change == 10.0
    assert loaded.picks[0].entry_price == 150.0

def test_save_portfolio_persists_aggregate_metrics(tmp_path):
    picks = [Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="x")]
    save_portfolio(
        picks, date="2024-01-01", output_dir=str(tmp_path), portfolio=PORTFOLIO,
        portfolio_return=5.5, spy_return=3.2, twr=0.08,
    )
    loaded = load_portfolio(output_dir=str(tmp_path), portfolio=PORTFOLIO)
    assert loaded.portfolio_return == 5.5
    assert loaded.spy_return == 3.2
    assert loaded.twr == 0.08
