"""Tests für Ticket 5: ConvictionScorer — Feinere LLM-basierte Score-Extraktion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingagents.portfolio.scorer import KeywordScorer
from tradingagents.portfolio.conviction import ConvictionScorer, ConvictionScore


class TestConvictionScore:
    def test_score_range_validation(self):
        with pytest.raises(ValueError):
            ConvictionScore(value=1.5)

    def test_score_range_min(self):
        with pytest.raises(ValueError):
            ConvictionScore(value=-1.5)

    def test_valid_score(self):
        cs = ConvictionScore(value=0.8)
        assert cs.value == 0.8

    def test_boundary_values_are_valid(self):
        assert ConvictionScore(value=1.0).value == 1.0
        assert ConvictionScore(value=-1.0).value == -1.0
        assert ConvictionScore(value=0.0).value == 0.0


class TestConvictionScorer:
    def _make_mock_client(self, return_value: float):
        """Erstellt einen Mock-instructor-Client der ConvictionScore direkt zurückgibt."""
        mock_client = MagicMock()
        # instructor-Pattern: create() gibt das Pydantic-Modell direkt zurück
        mock_client.chat.completions.create.return_value = ConvictionScore(value=return_value)
        return mock_client

    def test_score_strong_buy_returns_high_value(self):
        mock_client = self._make_mock_client(0.9)
        scorer = ConvictionScorer(client=mock_client)
        score = scorer.score("Strong BUY — fundamentals are excellent")
        assert score == 0.9

    def test_score_strong_sell_returns_negative_value(self):
        mock_client = self._make_mock_client(-0.8)
        scorer = ConvictionScorer(client=mock_client)
        score = scorer.score("Strong SELL — outlook is deteriorating")
        assert score == -0.8

    def test_fallback_to_keyword_on_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("LLM error")
        scorer = ConvictionScorer(client=mock_client)
        # Fallback: KeywordScorer → BUY = 1.0
        score = scorer.score("BUY")
        assert score == 1.0

    def test_fallback_for_sell_on_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("LLM error")
        scorer = ConvictionScorer(client=mock_client)
        score = scorer.score("SELL")
        assert score == -1.0

    def test_score_range_clamped_within_bounds(self):
        mock_client = self._make_mock_client(0.7)
        scorer = ConvictionScorer(client=mock_client)
        result = scorer.score("Cautious BUY — some risks remain")
        assert -1.0 <= result <= 1.0

    def test_llm_client_is_called_with_signal_text(self):
        mock_client = self._make_mock_client(0.5)
        scorer = ConvictionScorer(client=mock_client)
        scorer.score("Moderate BUY recommendation")
        mock_client.chat.completions.create.assert_called_once()

    def test_scorer_implements_base_scorer_interface(self):
        from tradingagents.portfolio.scorer import BaseScorer
        mock_client = self._make_mock_client(0.5)
        scorer = ConvictionScorer(client=mock_client)
        assert isinstance(scorer, BaseScorer)


class TestBatchRunnerWithConvictionScorer:
    def test_batch_runner_accepts_conviction_scorer(self):
        from tradingagents.portfolio.batch_runner import BatchRunner

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = ConvictionScore(value=0.7)
        scorer = ConvictionScorer(client=mock_client)

        def propagate_fn(ticker: str, date: str):
            return {"final_trade_decision": f"{ticker}: Strong BUY"}, "BUY"

        runner = BatchRunner(propagate_fn=propagate_fn, scorer=scorer)
        results = runner.run(["AAPL"], "2024-01-01")
        assert len(results) == 1
        assert results[0].score == 0.7
