"""Persistence for portfolio state (JSON-based).

Each portfolio lives in its own subdirectory under output_dir:
    <output_dir>/<portfolio>/
        state.json   -- unified portfolio state (current + history)
"""

from __future__ import annotations

import json
from pathlib import Path

from tradingagents.portfolio.models import Pick, Portfolio, PortfolioState, RebalanceEvent


def _portfolio_dir(output_dir: str, portfolio: str) -> Path:
    return Path(output_dir) / portfolio


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# PortfolioState (state.json)
# ---------------------------------------------------------------------------

def save_state(
    state: PortfolioState,
    output_dir: str = "portfolio_data",
    portfolio: str = "default",
) -> Path:
    """Write PortfolioState to state.json.

    Returns:
        Path to state.json.
    """
    path = _portfolio_dir(output_dir, portfolio) / "state.json"
    _write_json(path, state.model_dump())
    return path


def load_state(
    output_dir: str = "portfolio_data",
    portfolio: str = "default",
) -> PortfolioState:
    """Load state.json as PortfolioState.

    Returns:
        PortfolioState (empty if file does not exist).
    """
    file_path = _portfolio_dir(output_dir, portfolio) / "state.json"
    try:
        data = json.loads(file_path.read_text())
        return PortfolioState.model_validate(data)
    except FileNotFoundError:
        return PortfolioState()
    except (json.JSONDecodeError, Exception) as exc:
        raise ValueError(
            f"State file '{file_path}' is corrupted or has an unknown format: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Convenience: save / load current portfolio
# ---------------------------------------------------------------------------

def save_portfolio(
    picks: list[Pick],
    date: str,
    output_dir: str = "portfolio_data",
    portfolio: str = "default",
    *,
    portfolio_return: float | None = None,
    spy_return: float | None = None,
    twr: float | None = None,
) -> Path:
    """Save picks as current_portfolio in state.json.

    Returns:
        Path to state.json.
    """
    portfolio_obj = Portfolio(
        date=date,
        picks=picks,
        portfolio_return=portfolio_return,
        spy_return=spy_return,
        twr=twr,
    )
    state = load_state(output_dir, portfolio)
    state = state.model_copy(update={"current_portfolio": portfolio_obj})
    return save_state(state, output_dir, portfolio)


def load_portfolio(
    output_dir: str = "portfolio_data",
    portfolio: str = "default",
) -> Portfolio | None:
    """Load current_portfolio from state.json.

    Returns:
        Portfolio or None if not found.
    """
    state = load_state(output_dir, portfolio)
    return state.current_portfolio


# ---------------------------------------------------------------------------
# Rebalance: updates current_portfolio and appends snapshot
# ---------------------------------------------------------------------------

def archive_rebalance(
    event: RebalanceEvent,
    new_portfolio: Portfolio,
    output_dir: str = "portfolio_data",
    portfolio: str = "default",
) -> Path:
    """Persists a rebalance: updates current_portfolio and appends snapshot to state.json.

    Args:
        event: The rebalance event containing per-pick actions and period return.
        new_portfolio: The new active portfolio (HOLD + BUY picks only).
        output_dir: Base directory for portfolio data.
        portfolio: Portfolio name / subdirectory.

    Returns:
        Path to the written state.json.
    """
    state = load_state(output_dir, portfolio)

    snapshot = new_portfolio.model_copy(update={
        "portfolio_return": event.period_return,
    })
    updated_state = PortfolioState(
        current_portfolio=new_portfolio,
        past_portfolios=state.past_portfolios + [snapshot],
        rebalance_count=state.rebalance_count + 1,
    )
    return save_state(updated_state, output_dir, portfolio)
