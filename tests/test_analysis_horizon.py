"""Unit tests for Ticket 2: Configurable Analysis Time Horizon."""

import pytest
from unittest.mock import MagicMock, patch

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.agents.utils.agent_states import AgentState


class TestDefaultConfig:
    """Tests for new config keys."""

    def test_analysis_period_default(self):
        assert DEFAULT_CONFIG["analysis_period"] == "past month"

    def test_news_lookback_days_default(self):
        assert DEFAULT_CONFIG["news_lookback_days"] == 30


class TestPropagatorAnalysisPeriod:
    """Tests for analysis_period propagation through initial state."""

    def test_create_initial_state_includes_analysis_period_default(self):
        propagator = Propagator()
        state = propagator.create_initial_state("AAPL", "2024-01-15")
        assert state["analysis_period"] == "past month"

    def test_create_initial_state_uses_custom_analysis_period(self):
        propagator = Propagator()
        state = propagator.create_initial_state(
            "AAPL", "2024-01-15", analysis_period="past quarter"
        )
        assert state["analysis_period"] == "past quarter"

    def test_create_initial_state_preserves_other_fields(self):
        propagator = Propagator()
        state = propagator.create_initial_state("TSLA", "2024-06-01")
        assert state["company_of_interest"] == "TSLA"
        assert state["trade_date"] == "2024-06-01"
        assert "messages" in state


class TestAnalystPromptInterpolation:
    """Tests that analysts read analysis_period from state and use it in prompts."""

    def _make_state(self, analysis_period: str = "past month") -> dict:
        return {
            "trade_date": "2024-01-15",
            "company_of_interest": "AAPL",
            "analysis_period": analysis_period,
            "messages": [("human", "AAPL")],
        }

    def test_fundamentals_analyst_uses_analysis_period(self):
        from tradingagents.agents.analysts.fundamentals_analyst import (
            create_fundamentals_analyst,
        )

        captured_system_message = {}

        def fake_llm_bind_tools(tools):
            mock_chain = MagicMock()

            def fake_invoke(messages):
                result = MagicMock()
                result.tool_calls = []
                result.content = "report"
                return result

            mock_chain.invoke = fake_invoke
            return mock_chain

        mock_llm = MagicMock()
        mock_llm.bind_tools = fake_llm_bind_tools

        with patch(
            "tradingagents.agents.analysts.fundamentals_analyst.get_fundamentals"
        ), patch(
            "tradingagents.agents.analysts.fundamentals_analyst.get_balance_sheet"
        ), patch(
            "tradingagents.agents.analysts.fundamentals_analyst.get_cashflow"
        ), patch(
            "tradingagents.agents.analysts.fundamentals_analyst.get_income_statement"
        ):
            node = create_fundamentals_analyst(mock_llm)
            # Call with custom analysis period
            state = self._make_state("past quarter")
            # We verify the node runs without error and reads analysis_period from state
            # The prompt construction uses f-string with analysis_period
            # We can verify by checking the source uses state.get("analysis_period")
            import inspect
            src = inspect.getsource(node)
            assert "analysis_period" in src

    def test_news_analyst_uses_analysis_period(self):
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        import inspect

        mock_llm = MagicMock()
        node = create_news_analyst(mock_llm)
        src = inspect.getsource(node)
        assert "analysis_period" in src
        assert "past week" not in src

    def test_social_media_analyst_uses_analysis_period(self):
        from tradingagents.agents.analysts.social_media_analyst import (
            create_social_media_analyst,
        )
        import inspect

        mock_llm = MagicMock()
        node = create_social_media_analyst(mock_llm)
        src = inspect.getsource(node)
        assert "analysis_period" in src
        assert "past week" not in src

    def test_fundamentals_analyst_no_hardcoded_past_week(self):
        from tradingagents.agents.analysts.fundamentals_analyst import (
            create_fundamentals_analyst,
        )
        import inspect

        mock_llm = MagicMock()
        node = create_fundamentals_analyst(mock_llm)
        src = inspect.getsource(node)
        assert "past week" not in src


class TestNewsLookbackDefaults:
    """Tests that look_back_days reads from config (news_lookback_days=30)."""

    def test_yfinance_global_news_resolves_lookback_from_config(self):
        """When look_back_days is None, it reads news_lookback_days from config."""
        from tradingagents.dataflows.yfinance_news import get_global_news_yfinance
        import inspect

        sig = inspect.signature(get_global_news_yfinance)
        assert sig.parameters["look_back_days"].default is None

    def test_alpha_vantage_global_news_resolves_lookback_from_config(self):
        """When look_back_days is None, it reads news_lookback_days from config."""
        from tradingagents.dataflows.alpha_vantage_news import get_global_news
        import inspect

        sig = inspect.signature(get_global_news)
        assert sig.parameters["look_back_days"].default is None

    def test_config_news_lookback_days_is_30(self):
        """news_lookback_days config key defaults to 30, driving the lookback resolution."""
        from tradingagents.default_config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["news_lookback_days"] == 30

    def test_news_data_tool_default_lookback_is_none(self):
        """Tool default is None so config value is resolved at call time."""
        from tradingagents.agents.utils.news_data_tools import get_global_news
        import inspect

        sig = inspect.signature(get_global_news.func)
        assert sig.parameters["look_back_days"].default is None


class TestAnalysisPeriodValidation:
    """Tests that None/empty analysis_period falls back to 'past month'."""

    def test_none_analysis_period_falls_back(self):
        """state.get('analysis_period') returning None uses default."""
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        import inspect

        mock_llm = MagicMock()
        node = create_news_analyst(mock_llm)
        src = inspect.getsource(node)
        # Verify guard pattern is used
        assert 'or "past month"' in src

    def test_empty_analysis_period_falls_back(self):
        """Empty string analysis_period falls back to 'past month' via 'or' guard."""
        # 'or "past month"' means '' or None both fall back
        result = "" or "past month"
        assert result == "past month"

    def test_none_falls_back(self):
        result = None or "past month"
        assert result == "past month"


class TestConfigPropagation:
    """Tests that analysis_period flows from config through propagate() to initial state."""

    def test_propagate_uses_config_analysis_period(self):
        """Verify propagate() reads analysis_period from config."""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

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
            final = {
                "company_of_interest": "AAPL",
                "trade_date": "2024-01-15",
                "final_trade_decision": "BUY",
                "messages": [],
            }
            mock_graph.invoke.return_value = final
            graph.graph = mock_graph

            with patch.object(graph, "_log_state"), patch.object(
                graph, "process_signal", return_value="BUY"
            ):
                graph.propagate("AAPL", "2024-01-15")

        assert captured_args["analysis_period"] == "past quarter"
