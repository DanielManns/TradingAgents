"""Tests for Ticket 2: rebalance — after 30 days: sell, buy, or hold."""

from __future__ import annotations

import json

import pytest

from tradingagents.portfolio.models import MAX_PICKS, Pick, Portfolio, PortfolioState, RebalanceAction, RebalanceEntry, RebalanceEvent
from tradingagents.portfolio.persistence import save_portfolio, load_portfolio, load_state, archive_rebalance
from tradingagents.portfolio.rebalancer import Rebalancer

PORTFOLIO = "test"


def _make_pick(ticker: str, score: float, signal: str = "BUY") -> Pick:
    return Pick(ticker=ticker, score=score, signal=signal, decision_text=f"Decision for {ticker}")


# ---------------------------------------------------------------------------
# RebalanceAction enum
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", [RebalanceAction.HOLD, RebalanceAction.SELL, RebalanceAction.BUY])
def test_rebalance_action_enum_values_exist(action):
    assert action


# ---------------------------------------------------------------------------
# RebalanceEntry
# ---------------------------------------------------------------------------

def test_rebalance_entry_fields():
    pick = _make_pick("AAPL", 1.0)
    r = RebalanceEntry(pick=pick, action=RebalanceAction.HOLD, old_score=1.0, new_score=1.0)
    assert r.pick.ticker == "AAPL"
    assert r.action == RebalanceAction.HOLD
    assert r.old_score == 1.0
    assert r.new_score == 1.0


# ---------------------------------------------------------------------------
# Rebalancer core logic
# ---------------------------------------------------------------------------

class TestRebalancer:
    """Tests for the rebalancing logic."""

    def _rb(self, min_improvement: float = 0.3) -> Rebalancer:
        return Rebalancer(min_improvement=min_improvement)

    def test_hold_when_score_unchanged(self):
        old_picks = [_make_pick("AAPL", 1.0), _make_pick("MSFT", 0.0, "HOLD")]
        actions = {r.pick.ticker: r.action for r in self._rb().compute(old_picks, {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 0.1}, top_n=2)}
        assert actions["AAPL"] == RebalanceAction.HOLD
        assert actions["MSFT"] == RebalanceAction.HOLD

    def test_sell_and_buy_when_improvement_exceeds_hurdle(self):
        old_picks = [_make_pick("AAPL", 1.0), _make_pick("MSFT", 0.0, "HOLD")]
        actions = {r.pick.ticker: r.action for r in self._rb().compute(old_picks, {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 1.0}, top_n=2)}
        assert actions["AAPL"] == RebalanceAction.HOLD
        assert actions["MSFT"] == RebalanceAction.SELL
        assert actions["NVDA"] == RebalanceAction.BUY

    def test_no_replace_when_improvement_below_hurdle(self):
        old_picks = [_make_pick("AAPL", 1.0), _make_pick("MSFT", 0.0, "HOLD")]
        actions = {r.pick.ticker: r.action for r in self._rb(min_improvement=0.5).compute(old_picks, {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 0.2}, top_n=2)}
        assert RebalanceAction.SELL not in actions.values()
        assert RebalanceAction.BUY not in actions.values()

    def test_result_always_has_exactly_top_n_final_tickers(self):
        old_picks = [_make_pick(t, 1.0) for t in ["AAPL", "MSFT", "GOOG", "AMZN", "META"]]
        new_scores = {t: 1.0 for t in ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "V", "MA", "JPM"]}
        results = self._rb().compute(old_picks, new_scores, top_n=5)
        final = {r.pick.ticker for r in results if r.action in (RebalanceAction.HOLD, RebalanceAction.BUY)}
        assert len(final) == 5

    def test_old_score_and_new_score_populated(self):
        results = self._rb().compute([_make_pick("AAPL", 0.5)], {"AAPL": 1.0}, top_n=1)
        r = results[0]
        assert r.pick.ticker == "AAPL"
        assert r.old_score == 0.5
        assert r.new_score == 1.0

    def test_top_n_defaults_to_max_picks(self):
        rb = self._rb()
        import inspect
        sig = inspect.signature(rb.compute)
        assert sig.parameters["top_n"].default == MAX_PICKS


# ---------------------------------------------------------------------------
# Persistence: archive_rebalance
# ---------------------------------------------------------------------------

class TestHistoryArchiving:
    def _make_event(self, date: str = "2024-01-01", period_return: float | None = None, entries: list[RebalanceEntry] | None = None) -> RebalanceEvent:
        if entries is None:
            entries = [RebalanceEntry(pick=_make_pick("AAPL", 1.0), action=RebalanceAction.HOLD, old_score=1.0, new_score=1.0)]
        return RebalanceEvent(date=date, entries=entries, period_return=period_return)

    def test_archive_creates_state_json(self, tmp_path):
        new_portfolio = Portfolio(date="2024-02-01", picks=[_make_pick("AAPL", 1.0)])
        archive_rebalance(self._make_event(), new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert (tmp_path / PORTFOLIO / "state.json").exists()

    def test_archive_updates_current_portfolio(self, tmp_path):
        new_portfolio = Portfolio(date="2024-02-01", picks=[_make_pick("MSFT", 1.0)])
        archive_rebalance(self._make_event(), new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)
        loaded = load_portfolio(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert loaded.picks[0].ticker == "MSFT"

    def test_snapshot_appended_to_state(self, tmp_path):
        new_portfolio = Portfolio(date="2024-02-01", picks=[_make_pick("MSFT", 1.0)])
        archive_rebalance(self._make_event(period_return=0.05), new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)
        state = load_state(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert len(state.snapshots) == 1
        assert state.snapshots[0].picks[0].ticker == "MSFT"
        assert state.snapshots[0].portfolio_return == 0.05

    def test_rebalance_count_incremented(self, tmp_path):
        new_portfolio = Portfolio(date="2024-02-01", picks=[_make_pick("AAPL", 1.0)])
        archive_rebalance(self._make_event(), new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)
        state = load_state(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert state.rebalance_count == 1

    def test_none_period_return_stored_on_snapshot(self, tmp_path):
        new_portfolio = Portfolio(date="2024-02-01", picks=[_make_pick("AAPL", 1.0)])
        archive_rebalance(self._make_event(period_return=None), new_portfolio=new_portfolio, output_dir=str(tmp_path), portfolio=PORTFOLIO)
        state = load_state(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert state.snapshots[0].portfolio_return is None

    def test_multiple_rebalances_accumulate(self, tmp_path):
        # First rebalance
        new_portfolio1 = Portfolio(date="2024-02-01", picks=[_make_pick("MSFT", 1.0)])
        archive_rebalance(self._make_event(period_return=0.10), new_portfolio=new_portfolio1, output_dir=str(tmp_path), portfolio=PORTFOLIO)

        # Second rebalance
        new_portfolio2 = Portfolio(date="2024-03-01", picks=[_make_pick("GOOG", 1.0)])
        archive_rebalance(self._make_event(date="2024-03-01", period_return=0.05), new_portfolio=new_portfolio2, output_dir=str(tmp_path), portfolio=PORTFOLIO)

        state = load_state(output_dir=str(tmp_path), portfolio=PORTFOLIO)
        assert len(state.snapshots) == 2
        assert state.snapshots[0].picks[0].ticker == "MSFT"
        assert state.snapshots[1].picks[0].ticker == "GOOG"
        assert state.rebalance_count == 2


# ---------------------------------------------------------------------------
# Portfolio validation
# ---------------------------------------------------------------------------

class TestPortfolioValidation:
    def test_portfolio_accepts_max_picks(self):
        picks = [_make_pick(f"T{i:03d}", 1.0) for i in range(MAX_PICKS)]
        p = Portfolio(date="2024-01-01", picks=picks)
        assert len(p.picks) == MAX_PICKS

    def test_portfolio_rejects_over_max_picks(self):
        picks = [_make_pick(f"T{i:03d}", 1.0) for i in range(MAX_PICKS + 1)]
        with pytest.raises(Exception):
            Portfolio(date="2024-01-01", picks=picks)

    def test_portfolio_accepts_fewer_than_max(self):
        picks = [_make_pick("AAPL", 1.0)]
        p = Portfolio(date="2024-01-01", picks=picks)
        assert len(p.picks) == 1


# ---------------------------------------------------------------------------
# PortfolioHistory model
# ---------------------------------------------------------------------------

class TestPortfolioStateModel:
    def test_empty_state(self):
        s = PortfolioState()
        assert s.current_portfolio is None
        assert s.snapshots == []
        assert s.rebalance_count == 0

    def test_roundtrip(self):
        current = Portfolio(date="2024-02-01", picks=[_make_pick("MSFT", 1.0)])
        snap = Portfolio(date="2024-02-01", picks=[_make_pick("AAPL", 1.0)], portfolio_return=0.10)
        s = PortfolioState(current_portfolio=current, snapshots=[snap], rebalance_count=1)
        data = s.model_dump()
        loaded = PortfolioState.model_validate(data)
        assert loaded.current_portfolio.picks[0].ticker == "MSFT"
        assert loaded.snapshots[0].picks[0].ticker == "AAPL"
        assert loaded.snapshots[0].portfolio_return == 0.10
        assert loaded.rebalance_count == 1


# ---------------------------------------------------------------------------
# Portfolio isolation
# ---------------------------------------------------------------------------

class TestPortfolioIsolation:
    """Two portfolios must not interfere with each other."""

    def test_two_portfolios_independent(self, tmp_path):
        save_portfolio([_make_pick("AAPL", 1.0)], date="2024-01-01", output_dir=str(tmp_path), portfolio="alpha")
        save_portfolio([_make_pick("MSFT", 1.0)], date="2024-01-01", output_dir=str(tmp_path), portfolio="beta")

        alpha = load_portfolio(output_dir=str(tmp_path), portfolio="alpha")
        beta = load_portfolio(output_dir=str(tmp_path), portfolio="beta")

        assert alpha.picks[0].ticker == "AAPL"
        assert beta.picks[0].ticker == "MSFT"
