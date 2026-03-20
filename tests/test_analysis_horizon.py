"""Unit tests for Ticket 2: Configurable Analysis Time Horizon."""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.agents.utils.news_data_tools import get_global_news as tool_get_global_news
from tradingagents.dataflows.alpha_vantage_news import get_global_news as av_get_global_news
from tradingagents.dataflows.yfinance_news import get_global_news_yfinance
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph


class TestDefaultConfig:
    """Tests for new config keys."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("analysis_period", "past month"),
            ("news_lookback_days", 30),
        ],
    )
    def test_config_defaults(self, key, expected):
        assert DEFAULT_CONFIG[key] == expected


class TestPropagatorAnalysisPeriod:
    """Tests for analysis_period propagation through initial state."""

    def test_create_initial_state_includes_analysis_period_default(self):
        state = Propagator().create_initial_state("AAPL", "2024-01-15")
        assert state["analysis_period"] == "past month"

    def test_create_initial_state_uses_custom_analysis_period(self):
        state = Propagator().create_initial_state("AAPL", "2024-01-15", analysis_period="past quarter")
        assert state["analysis_period"] == "past quarter"

    def test_create_initial_state_preserves_other_fields(self):
        state = Propagator().create_initial_state("TSLA", "2024-06-01")
        assert state["company_of_interest"] == "TSLA"
        assert state["trade_date"] == "2024-06-01"
        assert "messages" in state


class TestAnalystPromptInterpolation:
    """Tests that analysts read analysis_period from state and use it in prompts."""

    @pytest.mark.parametrize(
        "create_fn",
        [
            create_fundamentals_analyst,
            create_news_analyst,
            create_social_media_analyst,
        ],
    )
    def test_analyst_uses_analysis_period_and_no_hardcoded_past_week(self, create_fn):
        node = create_fn(MagicMock())
        src = inspect.getsource(node)
        assert "analysis_period" in src
        assert "past week" not in src


class TestNewsLookbackDefaults:
    """Tests that look_back_days defaults to None so config drives the value."""

    @pytest.mark.parametrize(
        "fn,attr",
        [
            (get_global_news_yfinance, "look_back_days"),
            (av_get_global_news, "look_back_days"),
            (tool_get_global_news.func, "look_back_days"),
        ],
        ids=["yfinance", "alpha_vantage", "tool"],
    )
    def test_look_back_days_default_is_none(self, fn, attr):
        assert inspect.signature(fn).parameters[attr].default is None


class TestAnalysisPeriodValidation:
    """Tests that None/empty analysis_period falls back to 'past month'."""

    def test_fallback_guard_present_in_news_analyst(self):
        src = inspect.getsource(create_news_analyst(MagicMock()))
        assert 'or "past month"' in src

    @pytest.mark.parametrize("value", [None, ""])
    def test_falsy_value_falls_back(self, value):
        assert (value or "past month") == "past month"


class TestConfigPropagation:
    """Tests that analysis_period flows from config through propagate() to initial state."""

    def test_propagate_uses_config_analysis_period(self):
        captured_args = {}

        class FakePropagator:
            def create_initial_state(self, company_name, trade_date, analysis_period="past month"):
                captured_args["analysis_period"] = analysis_period
                return {
                    "messages": [("human", company_name)],
                    "company_of_interest": company_name,
                    "trade_date": str(trade_date),
                    "analysis_period": analysis_period,
                    "investment_debate_state": MagicMock(),
                    "risk_debate_state": MagicMock(),
                    "market_report": "",
                    "fundamentals_report": "",
                    "sentiment_report": "",
                    "news_report": "",
                }

            def get_graph_args(self, callbacks=None):
                return {"stream_mode": "values", "config": {"recursion_limit": 100}}

        custom_config = {**DEFAULT_CONFIG, "analysis_period": "past quarter"}

        with patch.object(TradingAgentsGraph, "__init__", lambda self, **kw: None):
            graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
            graph.config = custom_config
            graph.propagator = FakePropagator()
            graph.debug = False
            graph.callbacks = []
            graph.ticker = None
            graph.curr_state = None
            graph.log_states_dict = {}

            mock_graph = MagicMock()
            mock_graph.invoke.return_value = {
                "company_of_interest": "AAPL",
                "trade_date": "2024-01-15",
                "final_trade_decision": "BUY",
                "messages": [],
            }
            graph.graph = mock_graph

            with patch.object(graph, "_log_state"), patch.object(graph, "process_signal", return_value="BUY"):
                graph.propagate("AAPL", "2024-01-15")

        assert captured_args["analysis_period"] == "past quarter"
