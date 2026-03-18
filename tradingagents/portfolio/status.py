"""Portfolio-Status: Aktuelle Performance der gehaltenen Aktien."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class PortfolioEntry:
    ticker: str
    signal: str
    pick_date: str
    price_at_pick: float
    current_price: float
    pct_change: float


# Typ-Alias für die Preisfunktion: fetch(ticker, date=None) → float | None
PriceFetcher = Callable[[str, str | None], float | None]


class PortfolioStatus:
    """Baut Performance-Einträge für das Portfolio aus einem picks-Dict."""

    def __init__(self, price_fetcher: PriceFetcher):
        self.price_fetcher = price_fetcher

    def build(self, picks_payload: dict) -> list[PortfolioEntry]:
        """
        Erstellt PortfolioEntry-Liste aus einem load_picks()-Ergebnis.

        Args:
            picks_payload: Dict mit keys 'date' und 'picks' (wie load_picks() zurückgibt).

        Returns:
            Liste von PortfolioEntry, überspringe Ticker mit fehlenden Preisen.
        """
        pick_date = picks_payload["date"]
        entries: list[PortfolioEntry] = []

        for pick in picks_payload["picks"]:
            ticker = pick["ticker"]
            price_at_pick = self.price_fetcher(ticker, pick_date)
            current_price = self.price_fetcher(ticker, None)

            if price_at_pick is None or current_price is None:
                continue
            if price_at_pick == 0:
                continue

            pct = (current_price - price_at_pick) / price_at_pick * 100.0
            entries.append(PortfolioEntry(
                ticker=ticker,
                signal=pick.get("signal", "—"),
                pick_date=pick_date,
                price_at_pick=price_at_pick,
                current_price=current_price,
                pct_change=round(pct, 2),
            ))

        return entries

    def portfolio_avg_pct(self, entries: list[PortfolioEntry]) -> float:
        """Gleichgewichtete durchschnittliche Performance."""
        if not entries:
            return 0.0
        return sum(e.pct_change for e in entries) / len(entries)

    def spy_pct_change(self, pick_date: str, price_fetcher: PriceFetcher) -> float | None:
        """SPY-Performance seit pick_date als Benchmark."""
        price_then = price_fetcher("SPY", pick_date)
        price_now = price_fetcher("SPY", None)
        if price_then is None or price_now is None or price_then == 0:
            return None
        return round((price_now - price_then) / price_then * 100.0, 2)
