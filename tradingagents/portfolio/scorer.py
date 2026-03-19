"""Scoring-Interface und KeywordScorer für Trading-Signale."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class BaseScorer(ABC):
    """Basis-Interface für alle Scorer."""

    @abstractmethod
    def score(self, signal: str) -> float:
        """Gibt einen Float-Score aus einem Signal-String zurück."""


class KeywordScorer(BaseScorer):
    """Einfaches Keyword-Scoring: BUY=1.0, HOLD=0.0, SELL=-1.0."""

    def score(self, signal: str) -> float:
        upper = signal.strip().upper()
        if re.search(r"\bBUY\b", upper):
            return 1.0
        if re.search(r"\bSELL\b", upper):
            return -1.0
        return 0.0
