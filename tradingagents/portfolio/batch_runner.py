"""BatchRunner: runs propagate() over a list of tickers."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from tradingagents.portfolio.models import Pick
from tradingagents.portfolio.scorer import BaseScorer, KeywordScorer

if TYPE_CHECKING:
    from tradingagents.portfolio.cache import AnalysisCache


class BatchRunner:
    """Analyses a list of tickers via propagate() and returns sorted Picks."""

    def __init__(
        self,
        propagate_fn: Callable[[str, str], tuple],
        scorer: BaseScorer | None = None,
        delay_seconds: float = 0.0,
        cache: AnalysisCache | None = None,
        console: Console | None = None,
    ):
        self.propagate_fn = propagate_fn
        self.scorer = scorer or KeywordScorer()
        self.delay_seconds = delay_seconds
        self.cache = cache
        self._console = console or Console()

    def run(self, tickers: list[str], date: str) -> list[Pick]:
        """Analyse all tickers and return Picks sorted descending by score.

        Raises:
            RuntimeError: If more than half of all tickers fail.
        """
        results: list[Pick] = []
        failures = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self._console,
            transient=True,
        ) as progress:
            task = progress.add_task("Analysing tickers...", total=len(tickers))

            for ticker in tickers:
                progress.update(task, description=f"Analysing {ticker}...")
                try:
                    if self.cache is not None:
                        cached = self.cache.get(ticker, date)
                        if cached is not None:
                            signal = cached["signal"]
                            final_state = cached["final_state"]
                            progress.advance(task)
                            results.append(
                                Pick(
                                    ticker=ticker,
                                    score=self.scorer.score(signal),
                                    signal=signal,
                                    decision_text=final_state.get("final_trade_decision", ""),
                                )
                            )
                            continue

                    final_state, signal = self.propagate_fn(ticker, date)
                    decision_text = final_state.get("final_trade_decision", "")

                    if self.cache is not None:
                        self.cache.put(ticker, date, final_state, signal)

                    results.append(
                        Pick(
                            ticker=ticker,
                            score=self.scorer.score(signal),
                            signal=signal,
                            decision_text=decision_text,
                        )
                    )
                except Exception as exc:
                    failures += 1
                    self._console.print(f"[yellow]⚠ {ticker} skipped: {exc}[/yellow]")
                    progress.advance(task)
                    continue

                progress.advance(task)
                if self.delay_seconds > 0:
                    time.sleep(self.delay_seconds)

        if tickers and failures > len(tickers) // 2:
            raise RuntimeError(f"{failures}/{len(tickers)} analyses failed. Please check API key and connection.")

        results.sort(key=lambda r: (-r.score, r.ticker))
        return results
