"""Analyse-Cache: Speichert propagate()-Ergebnisse auf Disk mit TTL."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class AnalysisCache:
    """Disk-basierter Cache für propagate()-Ergebnisse (Key: ticker+date, TTL: konfigurierbar)."""

    def __init__(self, cache_dir: str = ".analysis_cache", ttl_days: int = 7):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_days * 86400

    def _key(self, ticker: str, date: str) -> str:
        raw = f"{ticker.upper()}_{date}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _file(self, ticker: str, date: str) -> Path:
        return self.cache_dir / f"{self._key(ticker, date)}.json"

    def get(self, ticker: str, date: str) -> dict | None:
        """Gibt gecachten Eintrag zurück, oder None wenn nicht vorhanden / abgelaufen."""
        f = self._file(ticker, date)
        if not f.exists():
            return None
        entry = json.loads(f.read_text())
        age = time.time() - entry["cached_at"]
        if self.ttl_seconds > 0 and age >= self.ttl_seconds:
            f.unlink(missing_ok=True)
            return None
        if self.ttl_seconds == 0:
            f.unlink(missing_ok=True)
            return None
        return {"final_state": entry["final_state"], "signal": entry["signal"]}

    def put(self, ticker: str, date: str, final_state: dict[str, Any], signal: str) -> None:
        """Speichert Ergebnis im Cache."""
        payload = {
            "ticker": ticker,
            "date": date,
            "signal": signal,
            "final_state": final_state,
            "cached_at": time.time(),
        }
        self._file(ticker, date).write_text(json.dumps(payload))
