"""Persistenz für Portfolio-Picks (JSON-basiert)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.portfolio.batch_runner import PickResult

PICKS_FILENAME = "latest_picks.json"


def save_picks(
    picks: list[PickResult],
    date: str,
    output_dir: str = "portfolio_data",
) -> Path:
    """Speichert Picks als JSON in output_dir/latest_picks.json."""
    dir_path = Path(output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "date": date,
        "picks": [
            {
                "ticker": p.ticker,
                "score": p.score,
                "signal": p.signal,
                "decision_text": p.decision_text,
            }
            for p in picks
        ],
    }

    out_file = dir_path / PICKS_FILENAME
    out_file.write_text(json.dumps(payload, indent=2))
    return out_file


def load_picks(output_dir: str = "portfolio_data") -> dict | None:
    """Lädt Picks aus output_dir/latest_picks.json. Gibt None zurück wenn nicht vorhanden."""
    file_path = Path(output_dir) / PICKS_FILENAME
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text())


def archive_picks(date: str, output_dir: str = "portfolio_data") -> Path | None:
    """Archiviert latest_picks.json als history/YYYY-MM-DD.json. Löscht latest_picks nicht."""
    latest = Path(output_dir) / PICKS_FILENAME
    if not latest.exists():
        return None
    history_dir = Path(output_dir) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_file = history_dir / f"{date}.json"
    archive_file.write_text(latest.read_text())
    return archive_file
