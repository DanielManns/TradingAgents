"""Rebalancer: Vergleicht alte Picks mit neuen Scores und empfiehlt HOLD/SELL/BUY."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RebalanceAction(str, Enum):
    HOLD = "HOLD"
    SELL = "SELL"
    BUY = "BUY"


@dataclass
class RebalanceResult:
    ticker: str
    action: RebalanceAction
    old_score: float
    new_score: float


class Rebalancer:
    """Berechnet Rebalancing-Aktionen basierend auf Score-Vergleich mit Hurdle-Rate."""

    def __init__(self, min_improvement: float = 0.3):
        """
        Args:
            min_improvement: Mindest-Score-Verbesserung eines neuen Kandidaten gegenüber
                             einem bestehenden Holding, damit ein Tausch stattfindet.
        """
        self.min_improvement = min_improvement

    def compute(
        self,
        old_picks: list[dict],
        new_scores: dict[str, float],
        top_n: int = 10,
    ) -> list[RebalanceResult]:
        """
        Berechnet Rebalancing-Aktionen.

        Args:
            old_picks: Liste von Pick-Dicts (keys: ticker, score) aus latest_picks.json.
            new_scores: Mapping ticker → neuer Score für alle analysierten Kandidaten.
            top_n: Ziel-Portfolio-Größe.

        Returns:
            Liste von RebalanceResult (HOLD für Beibehaltene, SELL+BUY für Tausche).
        """
        old_by_ticker = {p["ticker"]: p["score"] for p in old_picks}
        holdings = list(old_by_ticker.keys())

        # Kandidaten die nicht im aktuellen Portfolio sind, absteigend nach neuem Score
        candidates = sorted(
            [(t, s) for t, s in new_scores.items() if t not in old_by_ticker],
            key=lambda x: (-x[1], x[0]),
        )

        results: list[RebalanceResult] = []
        sells: list[str] = []
        buys: list[str] = []

        # Für jedes Holding: neuen Score holen, sonst alten behalten
        holding_new_scores = {t: new_scores.get(t, old_by_ticker[t]) for t in holdings}

        # Schlechteste Holdings absteigend nach neuem Score sortieren (schwächste zuerst)
        sorted_holdings = sorted(holdings, key=lambda t: holding_new_scores[t])

        remaining_candidates = list(candidates)

        # Greedy: Ersetze das schwächste Holding durch den besten Kandidaten, wenn Hurdle überschritten
        replaced: set[str] = set()
        bought: list[str] = []

        for holding in sorted_holdings:
            if not remaining_candidates:
                break
            best_candidate, best_score = remaining_candidates[0]
            current_score = holding_new_scores[holding]
            if best_score - current_score >= self.min_improvement:
                replaced.add(holding)
                bought.append(best_candidate)
                remaining_candidates.pop(0)

        # Ergebnisse zusammenstellen
        for ticker in holdings:
            action = RebalanceAction.SELL if ticker in replaced else RebalanceAction.HOLD
            results.append(RebalanceResult(
                ticker=ticker,
                action=action,
                old_score=old_by_ticker[ticker],
                new_score=holding_new_scores[ticker],
            ))

        for ticker in bought:
            results.append(RebalanceResult(
                ticker=ticker,
                action=RebalanceAction.BUY,
                old_score=0.0,
                new_score=new_scores[ticker],
            ))

        return results
