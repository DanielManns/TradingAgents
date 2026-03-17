"""Shared pytest fixtures for TradingAgents test suite."""

import pytest

from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def default_config() -> dict:
    """Provide a copy of the default config for testing."""
    return DEFAULT_CONFIG.copy()
