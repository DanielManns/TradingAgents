"""Persistenz für Portfolio-Picks (JSON-basiert)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from tradingagents.portfolio.batch_runner import PickResult

PICKS_FILENAME = "latest_picks.json"


class PickEntry(TypedDict):
    ticker: str
    score: float
    signal: str
    decision_text: str


class PicksFile(TypedDict):
    date: str
    picks: list[PickEntry]


def save_picks(
    picks: list[PickResult],
    date: str,
    output_dir: str = "portfolio_data",
) -> Path:
    """Speichert Picks als JSON in output_dir/latest_picks.json."""
    dir_path = Path(output_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    payload: PicksFile = {
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


def load_picks(output_dir: str = "portfolio_data") -> PicksFile | None:
    """Lädt Picks aus output_dir/latest_picks.json.

    Returns:
        PicksFile dict oder None wenn nicht vorhanden oder korrupt.
    """
    file_path = Path(output_dir) / PICKS_FILENAME
    try:
        content = file_path.read_text()
        data = json.loads(content)
        # Minimale Schema-Validierung
        _ = data["date"], data["picks"]
        return data
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, KeyError) as exc:
        raise ValueError(
            f"Portfolio-Datei '{file_path}' ist beschädigt oder hat ein unbekanntes Format: {exc}"
        ) from exc


def archive_picks(date: str, output_dir: str = "portfolio_data") -> Path | None:
    """Archiviert latest_picks.json als history/YYYY-MM-DD.json.

    Returns:
        Pfad zur archivierten Datei, oder None wenn keine latest_picks.json vorhanden.
    """
    latest = Path(output_dir) / PICKS_FILENAME
    try:
        content = latest.read_text()
    except FileNotFoundError:
        return None

    history_dir = Path(output_dir) / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_file = history_dir / f"{date}.json"
    archive_file.write_text(content)
    return archive_file
