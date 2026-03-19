"""Rebalancer: Vergleicht alte Picks mit neuen Scores und empfiehlt HOLD/SELL/BUY."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RebalanceAction(str, Enum):
    HOLD = "HOLD"
    SELL = "SELL"
    BUY = "BUY"


@dataclass(frozen=True)
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
        """Berechnet Rebalancing-Aktionen.

        Args:
            old_picks: Liste von Pick-Dicts (keys: ticker, score) aus latest_picks.json.
            new_scores: Mapping ticker → neuer Score für alle analysierten Kandidaten.
            top_n: Ziel-Portfolio-Größe. Das Ergebnis enthält genau top_n HOLD+BUY Positionen.

        Returns:
            Liste von RebalanceResult (HOLD für Beibehaltene, SELL+BUY für Tausche).
        """
        old_by_ticker = {p["ticker"]: p["score"] for p in old_picks}
        holdings = list(old_by_ticker.keys())

        # Neue Score für jedes Holding (Fallback: alter Score wenn nicht neu analysiert)
        holding_new_scores = {t: new_scores.get(t, old_by_ticker[t]) for t in holdings}

        # Kandidaten außerhalb des aktuellen Portfolios, absteigend nach neuem Score
        candidates = sorted(
            [(t, s) for t, s in new_scores.items() if t not in old_by_ticker],
            key=lambda x: (-x[1], x[0]),
        )

        # Greedy: schwächstes Holding durch besten Kandidaten ersetzen, wenn Hurdle überschritten
        sorted_holdings = sorted(holdings, key=lambda t: holding_new_scores[t])
        remaining_candidates = list(candidates)
        replaced: set[str] = set()
        bought: list[str] = []

        for holding in sorted_holdings:
            if not remaining_candidates:
                break
            best_candidate, best_score = remaining_candidates[0]
            if best_score - holding_new_scores[holding] >= self.min_improvement:
                replaced.add(holding)
                bought.append(best_candidate)
                remaining_candidates.pop(0)

        results: list[RebalanceResult] = []

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

        # Sicherstellen dass das Ergebnis-Portfolio genau top_n Positionen hat.
        # Sortiere HOLD+BUY nach neuem Score und behalte nur top_n davon.
        keepers = sorted(
            [r for r in results if r.action in (RebalanceAction.HOLD, RebalanceAction.BUY)],
            key=lambda r: (-r.new_score, r.ticker),
        )[:top_n]
        keeper_tickers = {r.ticker for r in keepers}

        # Positionen die durch top_n-Trimming rausfallen werden zu zusätzlichen SELLs
        final: list[RebalanceResult] = []
        for r in results:
            if r.action == RebalanceAction.SELL:
                final.append(r)
            elif r.ticker in keeper_tickers:
                final.append(r)
            else:
                final.append(RebalanceResult(
                    ticker=r.ticker,
                    action=RebalanceAction.SELL,
                    old_score=r.old_score,
                    new_score=r.new_score,
                ))

        return final
