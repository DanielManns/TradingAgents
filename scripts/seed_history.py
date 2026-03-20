"""Seed portfolio_data with fake history for visual TWR testing.

Usage:
    python scripts/seed_history.py [--output-dir portfolio_data] [--portfolio default] [--clean]

Creates two past rebalance events plus a current.json so that
`python -m cli.main status` shows a populated TWR line.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from tradingagents.portfolio.models import (
    Pick,
    Portfolio,
    RebalanceAction,
    RebalanceEntry,
    RebalanceEvent,
)
from tradingagents.portfolio.persistence import save_portfolio, archive_rebalance

PORTFOLIO = "default"

# Period 1: initial pick
_pick_1_picks = [
    Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="Strong momentum", entry_date="2026-02-01"),
    Pick(ticker="MSFT", score=1.0, signal="BUY", decision_text="Cloud growth", entry_date="2026-02-01"),
]

# Period 2: rebalance — sell AAPL, buy NVDA, hold MSFT
_rebalance_1 = RebalanceEvent(
    date="2026-03-01",
    entries=[
        RebalanceEntry(
            pick=Pick(ticker="AAPL", score=0.0, signal="SELL", decision_text="Taking profits", exit_date="2026-03-01", exit_price=185.0),
            action=RebalanceAction.SELL, old_score=1.0, new_score=0.0,
        ),
        RebalanceEntry(
            pick=Pick(ticker="NVDA", score=1.0, signal="BUY", decision_text="AI tailwind", entry_date="2026-03-01", entry_price=780.0),
            action=RebalanceAction.BUY, old_score=0.0, new_score=1.0,
        ),
        RebalanceEntry(
            pick=Pick(ticker="MSFT", score=0.0, signal="HOLD", decision_text="Hold steady"),
            action=RebalanceAction.HOLD, old_score=0.0, new_score=0.0,
        ),
    ],
    period_return=0.08,
)

_portfolio_after_reb1 = Portfolio(
    date="2026-03-01",
    picks=[
        Pick(ticker="NVDA", score=1.0, signal="BUY", decision_text="AI tailwind", entry_date="2026-03-01", entry_price=780.0),
        Pick(ticker="MSFT", score=0.0, signal="HOLD", decision_text="Hold steady"),
    ],
)

# Period 3: rebalance — sell MSFT, buy AAPL, hold NVDA
_rebalance_2 = RebalanceEvent(
    date="2026-03-20",
    entries=[
        RebalanceEntry(
            pick=Pick(ticker="MSFT", score=0.0, signal="SELL", decision_text="Rotate out", exit_date="2026-03-20", exit_price=410.0),
            action=RebalanceAction.SELL, old_score=0.0, new_score=0.0,
        ),
        RebalanceEntry(
            pick=Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="Strong buy", entry_date="2026-03-20", entry_price=190.0),
            action=RebalanceAction.BUY, old_score=0.0, new_score=1.0,
        ),
        RebalanceEntry(
            pick=Pick(ticker="NVDA", score=1.0, signal="BUY", decision_text="Strong buy"),
            action=RebalanceAction.HOLD, old_score=1.0, new_score=1.0,
        ),
    ],
    period_return=-0.04,
)

# Current portfolio after period 3
_current = Portfolio(
    date="2026-03-20",
    picks=[
        Pick(ticker="AAPL", score=1.0, signal="BUY", decision_text="Strong buy", entry_date="2026-03-20", entry_price=190.0),
        Pick(ticker="NVDA", score=1.0, signal="BUY", decision_text="Strong buy"),
    ],
)


def seed(output_dir: str, portfolio: str) -> None:
    # 1. Write initial portfolio
    save_portfolio(_pick_1_picks, date="2026-02-01", output_dir=output_dir, portfolio=portfolio)
    print(f"  written: state.json (initial picks)")

    # 2. First rebalance
    archive_rebalance(_rebalance_1, new_portfolio=_portfolio_after_reb1, output_dir=output_dir, portfolio=portfolio)
    print(f"  written: rebalance 1 (period_return={_rebalance_1.period_return:+.0%})")

    # 3. Second rebalance
    archive_rebalance(_rebalance_2, new_portfolio=_current, output_dir=output_dir, portfolio=portfolio)
    print(f"  written: rebalance 2 (period_return={_rebalance_2.period_return:+.0%})")

    # TWR
    twr = 1.0
    for r in [_rebalance_1.period_return, _rebalance_2.period_return]:
        if r is not None:
            twr *= 1.0 + r
    print(f"\nExpected TWR: {(twr - 1) * 100:+.2f}%  (run `python -m cli.main status` to verify)")


def clean(output_dir: str, portfolio: str) -> None:
    base = Path(output_dir) / portfolio
    removed = []

    for name in ("state.json",):
        f = base / name
        if f.exists():
            f.unlink()
            removed.append(str(f))

    if base.exists() and not any(base.iterdir()):
        base.rmdir()

    for r in removed:
        print(f"  removed: {r}")
    if not removed:
        print("  nothing to remove")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed portfolio history for TWR testing.")
    parser.add_argument("--output-dir", default="portfolio_data", help="Portfolio data directory")
    parser.add_argument("--portfolio", default=PORTFOLIO, help="Portfolio name (subfolder)")
    parser.add_argument("--clean", action="store_true", help="Remove seeded files instead of creating them")
    args = parser.parse_args()

    if args.clean:
        print(f"Cleaning seed data from '{args.output_dir}/{args.portfolio}'...")
        clean(args.output_dir, args.portfolio)
    else:
        print(f"Seeding history data into '{args.output_dir}/{args.portfolio}'...")
        seed(args.output_dir, args.portfolio)
