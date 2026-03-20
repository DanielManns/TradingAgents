"""BatchRunner: Führt propagate() über eine Liste von Tickern aus."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from tradingagents.portfolio.scorer import BaseScorer, KeywordScorer

if TYPE_CHECKING:
    from tradingagents.portfolio.cache import AnalysisCache


@dataclass(frozen=True)
class PickResult:
    ticker: str
    score: float
    signal: str
    decision_text: str
    entry_price: float | None = None


class BatchRunner:
    """Analysiert eine Liste von Tickern via propagate() und gibt sortierte PickResults zurück."""

    def __init__(
        self,
        propagate_fn: Callable[[str, str], tuple],
        scorer: BaseScorer | None = None,
        delay_seconds: float = 0.0,
        cache: "AnalysisCache | None" = None,
        console: Console | None = None,
    ):
        self.propagate_fn = propagate_fn
        self.scorer = scorer or KeywordScorer()
        self.delay_seconds = delay_seconds
        self.cache = cache
        self._console = console or Console()

    def run(self, tickers: list[str], date: str) -> list[PickResult]:
        """Analysiert alle Ticker und gibt nach Score absteigend sortierte PickResults zurück.

        Raises:
            RuntimeError: Wenn mehr als die Hälfte aller Ticker fehlschlagen.
        """
        results: list[PickResult] = []
        failures = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self._console,
            transient=True,
        ) as progress:
            task = progress.add_task("Analysiere Aktien...", total=len(tickers))

            for ticker in tickers:
                progress.update(task, description=f"Analysiere {ticker}...")
                try:
                    if self.cache is not None:
                        cached = self.cache.get(ticker, date)
                        if cached is not None:
                            signal = cached["signal"]
                            final_state = cached["final_state"]
                            progress.advance(task)
                            results.append(PickResult(
                                ticker=ticker,
                                score=self.scorer.score(signal),
                                signal=signal,
                                decision_text=final_state.get("final_trade_decision", ""),
                            ))
                            continue

                    final_state, signal = self.propagate_fn(ticker, date)
                    decision_text = final_state.get("final_trade_decision", "")

                    if self.cache is not None:
                        self.cache.put(ticker, date, final_state, signal)

                    results.append(PickResult(
                        ticker=ticker,
                        score=self.scorer.score(signal),
                        signal=signal,
                        decision_text=decision_text,
                    ))
                except Exception as exc:
                    failures += 1
                    self._console.print(f"[yellow]⚠ {ticker} übersprungen: {exc}[/yellow]")
                    progress.advance(task)
                    continue

                progress.advance(task)
                if self.delay_seconds > 0:
                    time.sleep(self.delay_seconds)

        if tickers and failures > len(tickers) // 2:
            raise RuntimeError(
                f"{failures}/{len(tickers)} Analysen fehlgeschlagen. "
                "Bitte API-Key und Verbindung prüfen."
            )

        results.sort(key=lambda r: (-r.score, r.ticker))
        return results
