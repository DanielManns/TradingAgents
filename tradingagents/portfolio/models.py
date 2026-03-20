"""Pydantic models for the portfolio package."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MAX_PICKS: int = 10
"""Hard cap on the number of active picks in a portfolio."""


class Pick(BaseModel):
    """A single stock pick — the core unit of a portfolio.

    Lifecycle: created during batch analysis (ticker/signal/score),
    enriched with entry_price at save time, then with current_price/pct_change
    for status display, and finally with exit_date/exit_price when sold.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    signal: str = ""
    decision_text: str = ""
    score: float = 0.0
    entry_date: str | None = None
    entry_price: float | None = None
    current_price: float | None = None
    pct_change: float | None = None
    exit_date: str | None = None
    exit_price: float | None = None


class Portfolio(BaseModel):
    """Current portfolio state: only active (unsold) picks, capped at MAX_PICKS."""

    date: str
    picks: Annotated[list[Pick], Field(max_length=MAX_PICKS)]
    portfolio_return: float | None = None
    spy_return: float | None = None
    twr: float | None = None


class PortfolioState(BaseModel):
    """Complete portfolio state: current holdings and historical snapshots."""

    current_portfolio: Portfolio | None = None
    snapshots: list[Portfolio] = []
    rebalance_count: int = 0


class RebalanceAction(str, Enum):
    HOLD = "HOLD"
    SELL = "SELL"
    BUY = "BUY"


class RebalanceEntry(BaseModel):
    """What happened to a single pick during rebalancing."""

    model_config = ConfigDict(frozen=True)

    pick: Pick
    action: RebalanceAction
    old_score: float
    new_score: float


class RebalanceEvent(BaseModel):
    """A complete rebalancing event: date, per-pick actions, and period return."""

    date: str
    entries: list[RebalanceEntry]
    period_return: float | None = None
