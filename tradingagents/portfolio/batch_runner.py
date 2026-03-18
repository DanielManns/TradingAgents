"""BatchRunner: Führt propagate() über eine Liste von Tickern aus."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from tradingagents.portfolio.scorer import BaseScorer, KeywordScorer

if TYPE_CHECKING:
    from tradingagents.portfolio.cache import AnalysisCache

console = Console()


@dataclass
class PickResult:
    ticker: str
    score: float
    signal: str
    decision_text: str


class BatchRunner:
    """Analysiert eine Liste von Tickern via propagate() und gibt sortierte PickResults zurück."""

    def __init__(
        self,
        propagate_fn: Callable[[str, str], tuple],
        scorer: BaseScorer | None = None,
        delay_seconds: float = 0.0,
        cache: "AnalysisCache | None" = None,
    ):
        self.propagate_fn = propagate_fn
        self.scorer = scorer or KeywordScorer()
        self.delay_seconds = delay_seconds
        self.cache = cache

    def run(self, tickers: list[str], date: str) -> list[PickResult]:
        """Analysiert alle Ticker und gibt nach Score absteigend sortierte PickResults zurück."""
        results: list[PickResult] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Analysiere Aktien...", total=len(tickers))

            for ticker in tickers:
                progress.update(task, description=f"Analysiere {ticker}...")
                try:
                    # Cache-Lookup
                    if self.cache is not None:
                        cached = self.cache.get(ticker, date)
                        if cached is not None:
                            final_state = cached["final_state"]
                            signal = cached["signal"]
                            progress.advance(task)
                            score = self.scorer.score(signal)
                            results.append(PickResult(
                                ticker=ticker,
                                score=score,
                                signal=signal,
                                decision_text=final_state.get("final_trade_decision", ""),
                            ))
                            continue

                    final_state, signal = self.propagate_fn(ticker, date)
                    decision_text = final_state.get("final_trade_decision", "")
                    score = self.scorer.score(signal)

                    # Cache-Store
                    if self.cache is not None:
                        self.cache.put(ticker, date, final_state, signal)

                    results.append(PickResult(
                        ticker=ticker,
                        score=score,
                        signal=signal,
                        decision_text=decision_text,
                    ))
                except Exception as exc:
                    console.print(f"[yellow]⚠ {ticker} übersprungen: {exc}[/yellow]")
                    progress.advance(task)
                    continue

                progress.advance(task)
                if self.delay_seconds > 0:
                    time.sleep(self.delay_seconds)

        # Sortiere: absteigend nach Score, bei Gleichstand alphabetisch nach Ticker
        results.sort(key=lambda r: (-r.score, r.ticker))
        return results
