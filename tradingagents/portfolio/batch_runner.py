"""run_batch: analyses tickers × dates via propagate() and returns sorted Picks."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from tradingagents.portfolio.models import Pick
from tradingagents.portfolio.scorer import BaseScorer, KeywordScorer


def run_batch(
    tickers: list[str],
    dates: list[date],
    propagate_fn: Callable[[str, str], tuple],
    scorer: BaseScorer | None = None,
    delay_seconds: float = 0.0,
    console: Console | None = None,
) -> dict[date, list[Pick]]:
    """Analyse all tickers for each date and return Picks sorted descending by score.

    Args:
        tickers: Stock tickers to analyse.
        dates: Trading dates to analyse.
        propagate_fn: Called as ``propagate_fn(ticker, date_iso_str)`` — receives
            the date as an ISO-format string.
        scorer: Scoring strategy (default: KeywordScorer).
        delay_seconds: Pause between individual analyses.
        console: Rich console for output.

    Returns:
        Mapping of each date to its sorted list of Picks.

    Raises:
        RuntimeError: If more than half of all tickers fail for any single date.
    """
    scorer = scorer or KeywordScorer()
    console = console or Console()
    total = len(tickers) * len(dates)
    results: dict[date, list[Pick]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Analysing tickers...", total=total)

        for d in dates:
            date_str = d.isoformat()
            day_results: list[Pick] = []
            failures = 0

            for ticker in tickers:
                progress.update(task, description=f"Analysing {ticker} ({date_str})...")
                try:
                    final_state, signal = propagate_fn(ticker, date_str)
                    decision_text = final_state.get("final_trade_decision", "")

                    day_results.append(
                        Pick(
                            ticker=ticker,
                            score=scorer.score(signal),
                            signal=signal,
                            decision_text=decision_text,
                        )
                    )
                except Exception as exc:
                    failures += 1
                    console.print(f"[yellow]⚠ {ticker} skipped: {exc}[/yellow]")
                    progress.advance(task)
                    continue

                progress.advance(task)
                if delay_seconds > 0:
                    time.sleep(delay_seconds)

            if tickers and failures > len(tickers) // 2:
                raise RuntimeError(
                    f"{failures}/{len(tickers)} analyses failed for {date_str}. Please check API key and connection."
                )

            day_results.sort(key=lambda r: (-r.score, r.ticker))
            results[d] = day_results

    return results
