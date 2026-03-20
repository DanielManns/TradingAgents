"""Seed portfolio_data with fake history for visual TWR testing.

Usage:
    python scripts/seed_history.py [--output-dir portfolio_data] [--clean]

Creates two past periods plus a current picks file so that
`python -m cli.main status` shows a populated TWR line.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PERIODS = [
    {
        "date": "2026-02-01",
        "picks": [
            {"ticker": "AAPL", "score": 1.0, "signal": "BUY", "decision_text": "Strong momentum"},
            {"ticker": "MSFT", "score": 1.0, "signal": "BUY", "decision_text": "Cloud growth"},
        ],
        "period_return": 0.08,  # +8% in February
    },
    {
        "date": "2026-03-01",
        "picks": [
            {"ticker": "NVDA", "score": 1.0, "signal": "BUY", "decision_text": "AI tailwind"},
            {"ticker": "MSFT", "score": 0.0, "signal": "HOLD", "decision_text": "Hold steady"},
        ],
        "period_return": -0.04,  # -4% in March
    },
]

LATEST_PICKS = {
    "date": "2026-03-20",
    "picks": [
        {"ticker": "AAPL", "score": 1.0, "signal": "BUY", "decision_text": "Strong buy"},
        {"ticker": "NVDA", "score": 1.0, "signal": "BUY", "decision_text": "Strong buy"},
    ],
}


def seed(output_dir: str) -> None:
    base = Path(output_dir)
    history_dir = base / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    for period in PERIODS:
        path = history_dir / f"{period['date']}.json"
        path.write_text(json.dumps(period, indent=2))
        print(f"  written: {path}  (period_return={period['period_return']:+.0%})")

    latest = base / "latest_picks.json"
    latest.write_text(json.dumps(LATEST_PICKS, indent=2))
    print(f"  written: {latest}")

    twr = 1.0
    for p in PERIODS:
        twr *= 1.0 + p["period_return"]
    print(f"\nExpected TWR: {(twr - 1) * 100:+.2f}%  (run `python -m cli.main status` to verify)")


def clean(output_dir: str) -> None:
    base = Path(output_dir)
    removed = []
    for period in PERIODS:
        path = base / "history" / f"{period['date']}.json"
        if path.exists():
            path.unlink()
            removed.append(str(path))
    latest = base / "latest_picks.json"
    if latest.exists():
        latest.unlink()
        removed.append(str(latest))
    for r in removed:
        print(f"  removed: {r}")
    if not removed:
        print("  nothing to remove")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed portfolio history for TWR testing.")
    parser.add_argument("--output-dir", default="portfolio_data", help="Portfolio data directory")
    parser.add_argument("--clean", action="store_true", help="Remove seeded files instead of creating them")
    args = parser.parse_args()

    if args.clean:
        print(f"Cleaning seed data from '{args.output_dir}'...")
        clean(args.output_dir)
    else:
        print(f"Seeding history data into '{args.output_dir}'...")
        seed(args.output_dir)
