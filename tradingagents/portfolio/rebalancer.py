"""Rebalancer: compares old picks with new scores and recommends HOLD/SELL/BUY."""

from __future__ import annotations

from tradingagents.portfolio.models import MAX_PICKS, Pick, RebalanceAction, RebalanceEntry


class Rebalancer:
    """Computes rebalancing actions based on score comparison with hurdle rate."""

    def __init__(self, min_improvement: float = 0.3):
        self.min_improvement = min_improvement

    def compute(
        self,
        old_picks: list[Pick],
        new_scores: dict[str, float],
        top_n: int = MAX_PICKS,
    ) -> list[RebalanceEntry]:
        """Compute rebalancing actions.

        Args:
            old_picks: List of Pick objects from the current portfolio.
            new_scores: Mapping ticker -> new score for all analysed candidates.
            top_n: Target portfolio size.

        Returns:
            List of RebalanceEntry (HOLD for kept, SELL+BUY for swaps).
        """
        old_by_ticker = {p.ticker: p for p in old_picks}
        holdings = list(old_by_ticker.keys())

        holding_new_scores = {t: new_scores.get(t, old_by_ticker[t].score) for t in holdings}

        candidates = sorted(
            [(t, s) for t, s in new_scores.items() if t not in old_by_ticker],
            key=lambda x: (-x[1], x[0]),
        )

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

        results: list[RebalanceEntry] = []

        for ticker in holdings:
            action = RebalanceAction.SELL if ticker in replaced else RebalanceAction.HOLD
            results.append(RebalanceEntry(
                pick=old_by_ticker[ticker],
                action=action,
                old_score=old_by_ticker[ticker].score,
                new_score=holding_new_scores[ticker],
            ))

        for ticker in bought:
            results.append(RebalanceEntry(
                pick=Pick(ticker=ticker),
                action=RebalanceAction.BUY,
                old_score=0.0,
                new_score=new_scores[ticker],
            ))

        keepers = sorted(
            [r for r in results if r.action in (RebalanceAction.HOLD, RebalanceAction.BUY)],
            key=lambda r: (-r.new_score, r.pick.ticker),
        )[:top_n]
        keeper_tickers = {r.pick.ticker for r in keepers}

        final: list[RebalanceEntry] = []
        for r in results:
            if r.action == RebalanceAction.SELL:
                final.append(r)
            elif r.pick.ticker in keeper_tickers:
                final.append(r)
            else:
                final.append(RebalanceEntry(
                    pick=r.pick,
                    action=RebalanceAction.SELL,
                    old_score=r.old_score,
                    new_score=r.new_score,
                ))

        return final
