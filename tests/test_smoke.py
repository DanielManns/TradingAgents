"""Smoke test to verify pytest collection and key imports work."""


def test_import_default_config() -> None:
    """Verify the tradingagents default_config is importable and well-formed."""
    from tradingagents.default_config import DEFAULT_CONFIG

    assert isinstance(DEFAULT_CONFIG, dict)
    assert "llm_provider" in DEFAULT_CONFIG
