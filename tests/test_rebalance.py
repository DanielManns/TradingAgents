"""Tests für Ticket 2: rebalance — Nach 30 Tagen: Verkaufen, Kaufen oder Halten."""

from __future__ import annotations

import json

import pytest

from tradingagents.portfolio.batch_runner import PickResult
from tradingagents.portfolio.persistence import save_picks, load_picks, archive_picks
from tradingagents.portfolio.rebalancer import Rebalancer, RebalanceAction, RebalanceResult


def _make_pick(ticker: str, score: float, signal: str = "BUY") -> PickResult:
    return PickResult(ticker=ticker, score=score, signal=signal, decision_text=f"Decision for {ticker}")


def _make_pick_dict(ticker: str, score: float, signal: str = "BUY") -> dict:
    return {"ticker": ticker, "score": score, "signal": signal, "decision_text": f"Decision for {ticker}"}


# ---------------------------------------------------------------------------
# RebalanceAction enum
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", [RebalanceAction.HOLD, RebalanceAction.SELL, RebalanceAction.BUY])
def test_rebalance_action_enum_values_exist(action):
    assert action


# ---------------------------------------------------------------------------
# RebalanceResult dataclass
# ---------------------------------------------------------------------------

def test_rebalance_result_fields():
    r = RebalanceResult(ticker="AAPL", action=RebalanceAction.HOLD, old_score=1.0, new_score=1.0)
    assert r.ticker == "AAPL"
    assert r.action == RebalanceAction.HOLD
    assert r.old_score == 1.0
    assert r.new_score == 1.0


# ---------------------------------------------------------------------------
# Rebalancer core logic
# ---------------------------------------------------------------------------

class TestRebalancer:
    """Tests für die Rebalancing-Logik."""

    def _rb(self, min_improvement: float = 0.3) -> Rebalancer:
        return Rebalancer(min_improvement=min_improvement)

    def test_hold_when_score_unchanged(self):
        # NVDA score 0.1, MSFT score 0.0 → diff 0.1 < min_improvement 0.3 → kein Tausch
        old_picks = [_make_pick_dict("AAPL", 1.0), _make_pick_dict("MSFT", 0.0, "HOLD")]
        actions = {r.ticker: r.action for r in self._rb().compute(old_picks, {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 0.1}, top_n=2)}
        assert actions["AAPL"] == RebalanceAction.HOLD
        assert actions["MSFT"] == RebalanceAction.HOLD

    def test_sell_and_buy_when_improvement_exceeds_hurdle(self):
        # MSFT (score 0.0) should be replaced by NVDA (score=1.0, diff=1.0 > 0.3)
        old_picks = [_make_pick_dict("AAPL", 1.0), _make_pick_dict("MSFT", 0.0, "HOLD")]
        actions = {r.ticker: r.action for r in self._rb().compute(old_picks, {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 1.0}, top_n=2)}
        assert actions["AAPL"] == RebalanceAction.HOLD
        assert actions["MSFT"] == RebalanceAction.SELL
        assert actions["NVDA"] == RebalanceAction.BUY

    def test_no_replace_when_improvement_below_hurdle(self):
        # NVDA has score 0.2, MSFT has score 0.0 → diff 0.2 < 0.5, no swap
        old_picks = [_make_pick_dict("AAPL", 1.0), _make_pick_dict("MSFT", 0.0, "HOLD")]
        actions = {r.ticker: r.action for r in self._rb(min_improvement=0.5).compute(old_picks, {"AAPL": 1.0, "MSFT": 0.0, "NVDA": 0.2}, top_n=2)}
        assert RebalanceAction.SELL not in actions.values()
        assert RebalanceAction.BUY not in actions.values()

    def test_result_always_has_exactly_top_n_final_tickers(self):
        old_picks = [_make_pick_dict(t, 1.0) for t in ["AAPL", "MSFT", "GOOG", "AMZN", "META"]]
        new_scores = {t: 1.0 for t in ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA", "TSLA", "V", "MA", "JPM"]}
        results = self._rb().compute(old_picks, new_scores, top_n=5)
        final = {r.ticker for r in results if r.action in (RebalanceAction.HOLD, RebalanceAction.BUY)}
        assert len(final) == 5

    def test_old_score_and_new_score_populated(self):
        results = self._rb().compute([_make_pick_dict("AAPL", 0.5)], {"AAPL": 1.0}, top_n=1)
        r = results[0]
        assert r.ticker == "AAPL"
        assert r.old_score == 0.5
        assert r.new_score == 1.0


# ---------------------------------------------------------------------------
# Persistence: history archiving
# ---------------------------------------------------------------------------

class TestHistoryArchiving:
    def _setup(self, tmp_path):
        save_picks([_make_pick("AAPL", 1.0)], date="2024-01-01", output_dir=str(tmp_path))

    def test_archive_creates_history_dir(self, tmp_path):
        self._setup(tmp_path)
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        assert (tmp_path / "history").exists()

    def test_archive_saves_dated_file(self, tmp_path):
        self._setup(tmp_path)
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        assert (tmp_path / "history" / "2024-01-01.json").exists()

    def test_archive_does_not_delete_latest(self, tmp_path):
        from tradingagents.portfolio.persistence import PICKS_FILENAME
        self._setup(tmp_path)
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        assert (tmp_path / PICKS_FILENAME).exists()

    @pytest.mark.parametrize("period_return,expected", [(0.05, 0.05), (None, None)])
    def test_archive_stores_period_return(self, tmp_path, period_return, expected):
        self._setup(tmp_path)
        archive_picks(date="2024-01-01", period_return=period_return, output_dir=str(tmp_path))
        data = json.loads((tmp_path / "history" / "2024-01-01.json").read_text())
        assert data["period_return"] == expected

    def test_hold_action_has_null_price(self, tmp_path):
        self._setup(tmp_path)
        transactions = [{"ticker": "AAPL", "action": "HOLD", "action_price": None,
                         "score": 1.0, "signal": "BUY", "decision_text": "x"}]
        archive_picks(date="2024-01-01", transactions=transactions, output_dir=str(tmp_path))
        picks = json.loads((tmp_path / "history" / "2024-01-01.json").read_text())["picks"]
        aapl = next(p for p in picks if p["ticker"] == "AAPL")
        assert aapl["action"] == "HOLD"
        assert aapl["action_price"] is None

    def test_sell_action_stores_exit_price(self, tmp_path):
        self._setup(tmp_path)
        transactions = [{"ticker": "AAPL", "action": "SELL", "action_price": 175.50,
                         "score": -1.0, "signal": "SELL", "decision_text": "x"}]
        archive_picks(date="2024-01-01", transactions=transactions, output_dir=str(tmp_path))
        picks = json.loads((tmp_path / "history" / "2024-01-01.json").read_text())["picks"]
        aapl = next(p for p in picks if p["ticker"] == "AAPL")
        assert aapl["action"] == "SELL"
        assert aapl["action_price"] == 175.50

    def test_buy_action_appended_with_entry_price(self, tmp_path):
        # AAPL is in old picks; NVDA is a new BUY — must be appended
        self._setup(tmp_path)
        transactions = [
            {"ticker": "AAPL", "action": "HOLD", "action_price": None,
             "score": 1.0, "signal": "BUY", "decision_text": "hold"},
            {"ticker": "NVDA", "action": "BUY",  "action_price": 485.20,
             "score": 1.0, "signal": "BUY", "decision_text": "strong buy"},
        ]
        archive_picks(date="2024-01-01", transactions=transactions, output_dir=str(tmp_path))
        picks = json.loads((tmp_path / "history" / "2024-01-01.json").read_text())["picks"]
        tickers = [p["ticker"] for p in picks]
        assert "NVDA" in tickers
        nvda = next(p for p in picks if p["ticker"] == "NVDA")
        assert nvda["action"] == "BUY"
        assert nvda["action_price"] == 485.20

    def test_no_transactions_leaves_picks_unchanged(self, tmp_path):
        self._setup(tmp_path)
        archive_picks(date="2024-01-01", output_dir=str(tmp_path))
        picks = json.loads((tmp_path / "history" / "2024-01-01.json").read_text())["picks"]
        assert "action" not in picks[0]
        assert "action_price" not in picks[0]
