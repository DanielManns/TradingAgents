# Portfolio Management System - Implementation Plan

## Overview

Extend TradingAgents from single-stock BUY/HOLD/SELL recommendations into a full portfolio management system: 10-15 large-cap stocks from global developed markets, monthly rebalancing with transaction cost awareness, backtesting, and systematic evaluation of prediction quality.

**Principle — no fork:** The existing single-stock pipeline (`TradingAgentsGraph.propagate()`) stays untouched. New code wraps it at a higher level.

**Principle — minimal code:** Write only the least amount of custom code necessary. If a well-maintained Python library already implements a piece of functionality, use it instead of building from scratch. Glue code and thin wrappers are preferred over reimplementation. Every ticket should start by asking: "Is there a library that already does this?"

**New packages:** `tradingagents/portfolio/`, `tradingagents/backtest/`, `tradingagents/evaluation/`, `tests/`

**Key libraries (new dependencies):**

| Library | Purpose | Replaces custom code in |
|---------|---------|------------------------|
| `PyPortfolioOpt` | Position sizing, weight constraints, sector caps, discrete allocation | Tickets 8, 9, 10 |
| `bt` + `ffn` | Backtesting replay, rebalancing simulation, built-in performance stats | Ticket 11 |
| `pandera` | DataFrame schema validation (stale prices, NaN, gaps) | Ticket 3 |
| `sqlite-utils` | Zero-boilerplate SQLite (insert dicts, auto-schema, queries) | Ticket 7 |
| `instructor` | Structured LLM output extraction with Pydantic validation + retries | Ticket 5 |
| `quantstats` | Performance metrics + HTML tearsheets | Ticket 12 |

**Tooling:** `uv` for dependency resolution/installation (keep `setuptools` as build backend). `pytest` for testing. GitHub Actions for CI.

**Process:** Each ticket = feature branch → tests pass → merge to main. This plan file lives in the repo at `PLAN.md` and is updated after each ticket.

---

## Tickets (priority order)

### Ticket 1: Project Setup & Tooling — `feature/project-setup`
- [ ] **Add** `uv.lock` and update dev workflow to use `uv sync` / `uv run` (keep `setuptools` as build backend in `pyproject.toml`)
- [ ] **Create** `tests/__init__.py`, `tests/conftest.py` with basic pytest setup
- [ ] **Modify** `pyproject.toml` — add `[tool.pytest.ini_options]`, add `pytest`, `pytest-mock` to `[project.optional-dependencies]` dev group
- [ ] **Create** `.github/workflows/ci.yml` — GitHub Actions: install with `uv`, run `pytest tests/`
- [ ] **AC:** `uv sync` installs all deps; `uv run pytest tests/` passes (empty suite); CI runs on push
- [ ] **Tests:** Verify pytest collection works
- [ ] **Note:** `backtrader`, `rich`, `typer`, and CLI entry point already exist in `pyproject.toml` — no need to re-add

### Ticket 2: Configurable Analysis Time Horizon — `feature/analysis-horizon`
- [ ] **Modify** `tradingagents/agents/analysts/fundamentals_analyst.py:22` — replace hardcoded "past week" with configurable `{analysis_period}` (default "past month")
- [ ] **Modify** `tradingagents/agents/analysts/news_analyst.py:19` — same: "past week" → `{analysis_period}`
- [ ] **Modify** `tradingagents/agents/analysts/social_media_analyst.py:19` — same: "past week" → `{analysis_period}`
- [ ] **Modify** `tradingagents/dataflows/yfinance_news.py:107` — change default `look_back_days` from 7 to 30
- [ ] **Modify** `tradingagents/dataflows/alpha_vantage_news.py:25` — change default `look_back_days` from 7 to 30
- [ ] **Modify** `tradingagents/default_config.py` — add `analysis_period` (default "past month"), `news_lookback_days` (default 30)
- [ ] **AC:** Running `propagate()` with default config uses "past month" in analyst prompts and 30-day news lookback
- [ ] **Tests:** Unit tests verify prompt interpolation and config propagation

### Ticket 3: Stock Universe & Screening — `feature/stock-universe`
- [ ] **Create** `tradingagents/portfolio/__init__.py`
- [ ] **Create** `tradingagents/portfolio/universe.py` — `StockUniverse` class: maintains a **static curated seed list** of ~50 large-cap tickers from major global exchanges (US, Europe, Japan, UK) as the primary source. Uses YFinance only to **validate and enrich** seed tickers (current market cap, sector, exchange) — not to discover new tickers. Support filtering by market cap, sector, exchange. Cache enriched data to `portfolio_data/universe.json`
- [ ] **Create** `tradingagents/portfolio/data_validation.py` — use **`pandera`** to define DataFrame schemas for YFinance data (price > 0, no NaN in close, monotonic date index, no gaps > 5 business days). Thin wrapper returning validation report with warnings. Used by universe screening and batch analysis
- [ ] **Modify** `tradingagents/default_config.py` — add `portfolio` config section: `min_market_cap` (default 50B for large-cap), `max_candidates`, `portfolio_data_dir`
- [ ] **AC:** `StockUniverse(config).get_candidates(30)` returns up to 30 validated tickers with sector/exchange info from global markets; stale/missing data flagged
- [ ] **Tests:** Mock YFinance; verify filtering, caching, global market coverage, data validation

### Ticket 4: Batch Analysis Orchestrator — `feature/batch-analysis`
- [ ] **Create** `tradingagents/portfolio/batch_analyzer.py` — `BatchAnalyzer`: loops `propagate()` over ticker list, collects results, skips failures gracefully, supports progress callback. Includes **rate limiting** (configurable delay between API calls) and **cost estimation** (log estimated LLM token usage per run)
- [ ] **Modify** `tradingagents/graph/trading_graph.py` — add `reset_state()` method to clear `self.curr_state`, `self.ticker`, `self.log_states_dict` between runs
- [ ] **Modify** `tradingagents/default_config.py` — add `batch_delay_seconds` (default 1), `dry_run` (default False — skips LLM calls, returns mock results for pipeline testing)
- [ ] **AC:** Analyzes 3+ tickers; failures on one don't block others; results serializable to JSON; rate limiting respected; dry-run mode works without LLM calls
- [ ] **Tests:** Mock `propagate()`; verify error isolation, result collection, progress callbacks, rate limiting, dry-run mode

### Ticket 5: Signal Scoring & Ranking — `feature/signal-scoring`
- [ ] **Create** `tradingagents/portfolio/scoring.py` — `SignalScorer`: uses **`instructor`** with a Pydantic model to extract structured conviction score (-1.0 to +1.0) + signal enum (BUY/HOLD/SELL) from `final_trade_decision` text. `instructor` handles retries on validation failure. `rank_candidates()` sorts by conviction. Keyword fallback if LLM fails (BUY=0.5, HOLD=0.0, SELL=-0.5). **Clamp** scores outside [-1, 1] via Pydantic validator. Log and flag low-confidence or ambiguous extractions (e.g., "cautious buy", "weak hold") for review
- [ ] **AC:** Strong BUY > 0.5, strong SELL < -0.5, HOLD near 0; ranking correct; out-of-range scores clamped; ambiguous signals logged
- [ ] **Tests:** Mock LLM; test with known signal texts; verify fallback logic; verify clamping; test ambiguous signal handling

### Ticket 6: Portfolio State Management — `feature/portfolio-state`
- [ ] **Create** `tradingagents/portfolio/models.py` — dataclasses: `Position`, `Transaction`, `PortfolioSnapshot`, `PortfolioState`
- [ ] **Create** `tradingagents/portfolio/state_manager.py` — `PortfolioStateManager`: init, load, save, record transactions, take snapshots, validate (no selling unheld shares, no overspending cash). JSON persistence in `portfolio_data/` (DB migration planned later)
- [ ] **Modify** `tradingagents/default_config.py` — add `starting_cash` (default 1_000_000), `transaction_cost_bps` (default 10)
- [ ] **AC:** CRUD round-trips via JSON; rejects invalid transactions; snapshots with current prices
- [ ] **Tests:** Full state lifecycle tests; edge cases (overdraw, short sell rejection)

### Ticket 7: Analysis Results Database — `feature/results-database`
- [ ] **Create** `tradingagents/portfolio/database.py` — `AnalysisDatabase`: stores analysis results (ticker, date, signal, conviction score, full state JSON, model used, timestamp) in SQLite (`sqlite3` stdlib). Query by ticker, date range, model. Replaces/supplements `eval_results/` JSON logging
- [ ] **Modify** `tradingagents/graph/trading_graph.py` — optionally write to DB after each `propagate()` call
- [ ] **AC:** Analysis results persist across runs; queryable by ticker+date+model; existing JSON logging still works
- [ ] **Tests:** CRUD operations, query filters, schema migration
- [ ] **Note:** Moved earlier (was Ticket 10) because Tickets 11, 13, 14 depend on it, and portfolio construction benefits from queryable storage from the start

### Ticket 8: Position Sizing & Constraints — `feature/position-sizing`
- [ ] **Create** `tradingagents/portfolio/position_sizing.py` — `EqualWeightSizer` (default). Base class `PositionSizer` for future strategies. Accepts ranked stocks + portfolio state, returns target allocations
- [ ] **Create** `tradingagents/portfolio/constraints.py` — `PortfolioConstraints`: max stocks per sector, min sectors, max single-stock weight; `validate_portfolio()` reports violations. Optional (None = disabled)
- [ ] **Modify** `tradingagents/default_config.py` — add `target_num_holdings` (12), `max_position_pct` (0.10), `max_stocks_per_sector` (3), `min_sectors` (4)
- [ ] **AC:** 12 stocks with $1M → ~$83K each; sector caps enforced; constraints optional
- [ ] **Tests:** Sizing math; constraint enforcement; edge cases (fewer candidates than target)

### Ticket 9: Portfolio Construction — `feature/portfolio-construction`
- [ ] **Create** `tradingagents/portfolio/constructor.py` — `PortfolioConstructor.build_initial_portfolio(date, config)`: orchestrates universe screening → data validation → batch analysis → scoring → constraints → sizing → transactions → snapshot. Stores analysis results in DB (Ticket 7)
- [ ] **AC:** Given a date and config, produces a portfolio of 10-15 stocks with full audit trail; data validation warnings surfaced
- [ ] **Tests:** Integration test with all components mocked at boundaries

### Ticket 10: Monthly Rebalancing with Transaction Cost Awareness — `feature/rebalancing`
- [ ] **Create** `tradingagents/portfolio/rebalancer.py` — `PortfolioRebalancer.rebalance(portfolio, date, config)`:
  1. Re-analyze current holdings + screen new candidates
  2. Score all together
  3. **Transaction cost hurdle:** only replace if score improvement > `min_score_improvement` (default 0.15)
  4. `max_turnover_pct` (default 0.30) caps changes per rebalance
  5. Sells before buys to free cash; transaction costs deducted
- [ ] **Modify** `tradingagents/default_config.py` — add `min_score_improvement` (default 0.15), `max_turnover_pct` (default 0.30)
- [ ] **AC:** Holding at 0.6 NOT replaced by candidate at 0.7 (gap < 0.15); holding at 0.3 IS replaced by candidate at 0.8 (gap > 0.15); turnover capped
- [ ] **Tests:** Test hurdle logic, turnover cap, sell-before-buy ordering, cost deduction

### Ticket 11: Backtesting Engine — `feature/backtesting`
- [ ] **Create** `tradingagents/backtest/__init__.py`
- [ ] **Create** `tradingagents/backtest/engine.py` — `BacktestEngine.run(start_date, end_date, config)`: lightweight custom month-by-month loop using `PortfolioConstructor` then `PortfolioRebalancer`. Replays monthly snapshots with price lookups from YFinance. No external backtesting framework — keeps it simple and avoids unmaintained dependencies
- [ ] **Create** `tradingagents/backtest/data_feeds.py` — YFinance historical price adapter: fetches OHLCV for date ranges, caches to disk
- [ ] **Create** `tradingagents/backtest/analysis_cache.py` — caches LLM analysis results to disk (ticker+date → signal). Re-runs skip `propagate()` on cache hit. Essential for fast iteration
- [ ] **Modify** `tradingagents/default_config.py` — add `backtest` section with `cache_analyses` (default True)
- [ ] **AC:** 12-month backtest produces monthly portfolio values; second run uses cache (no LLM calls)
- [ ] **Tests:** Test with synthetic data; verify caching; verify month-by-month progression
- [ ] **Note:** Removed `backtrader` dependency (unmaintained since 2019). Custom replay loop is simpler for pre-computed monthly orders

### Ticket 12: Performance Metrics — `feature/performance-metrics`
- [ ] **Add** `quantstats` as dependency (Sharpe, Sortino, max drawdown, alpha/beta, 40+ metrics, HTML tearsheet). Fallback: `empyrical` or manual metric computation if `quantstats` proves problematic (sporadic maintenance)
- [ ] **Create** `tradingagents/portfolio/metrics.py` — thin wrapper around `quantstats`: `compute_metrics(portfolio_values, benchmark="SPY")` returns metrics dict; `generate_report(output_path)` creates HTML tearsheet
- [ ] **Create** `tradingagents/portfolio/benchmark.py` — `BenchmarkProvider`: fetches SPY or configurable benchmark via YFinance
- [ ] **AC:** Metrics match QuantStats output for known inputs; HTML report generated
- [ ] **Tests:** Verify wrapper with synthetic return series

### Ticket 13: Prediction Consistency Evaluation — `feature/prediction-consistency`
- [ ] **Create** `tradingagents/evaluation/__init__.py`
- [ ] **Create** `tradingagents/evaluation/consistency.py` — `ConsistencyEvaluator`: runs the same analysis N times for a given ticker+date with the same model/data, measures agreement rate (% of runs with same BUY/HOLD/SELL), score variance, and confidence intervals. Stores results in DB (Ticket 7)
- [ ] **AC:** For a given ticker+date, running 5 analyses shows agreement rate and score distribution
- [ ] **Tests:** Mock propagate with deterministic and varied outputs; verify stats calculations

### Ticket 14: Cross-Model Comparison — `feature/model-comparison`
- [ ] **Create** `tradingagents/evaluation/model_comparison.py` — `ModelComparator`: runs the same ticker+date analysis across multiple LLM configurations (e.g., GPT-4o, Claude, Gemini), compares signals, scores, and reasoning. Generates comparison report. Uses DB (Ticket 7) to store/retrieve results per model
- [ ] **AC:** Compare 2+ models on same ticker+date; report shows agreement/disagreement, score deltas, reasoning diffs
- [ ] **Tests:** Mock multiple model configs; verify comparison logic and report generation

### Ticket 15: CLI Integration — `feature/portfolio-cli`
- [ ] **Create** `cli/portfolio_commands.py` — Typer subcommands:
  - `portfolio init` — initialize portfolio (universe, starting cash, constraints)
  - `portfolio build --date YYYY-MM-DD` — initial construction
  - `portfolio rebalance --date YYYY-MM-DD` — monthly rebalance
  - `portfolio status` — current holdings, P&L, allocation (Rich table)
  - `portfolio history` — transaction history
  - `portfolio backtest --start --end` — run backtest with progress bar + metrics
  - `portfolio evaluate --ticker --date` — run consistency/model comparison
- [ ] **Modify** `cli/main.py` — register portfolio subcommand group
- [ ] **AC:** All commands work end-to-end with Rich output
- [ ] **Tests:** CLI invocation tests with mocked backends

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Build backend | `setuptools` (unchanged) | `uv` is a package manager, not a build backend — keep them separate |
| Dependency mgmt | `uv` for resolution/installation | Fast, reliable, user preference |
| Storage (phase 1) | JSON files in `portfolio_data/` | Simple start; matches existing patterns |
| Storage (phase 2) | SQLite for analysis results (Ticket 7) | Queryable, persistent, no server needed; introduced early so downstream tickets build on it |
| Performance metrics | QuantStats library (fallback: `empyrical`) | 40+ metrics, HTML tearsheets — minimal custom code. Fallback noted due to sporadic maintenance |
| Backtesting | Custom lightweight replay loop | `backtrader` is unmaintained (last release 2019); custom loop is simpler for pre-computed monthly orders |
| Scoring | LLM extracts conviction float from `final_trade_decision` | Reuses `SignalProcessor` pattern; no pipeline modification. Scores clamped to [-1, 1] |
| Core pipeline | Unchanged (except configurable time horizon) | New code calls `propagate()`, never forks it |
| Position sizing | Equal weight (default), pluggable | User preference; extensible later |
| Universe | Static curated global large-cap seed list; YFinance for validation/enrichment only | YFinance screener unreliable for non-US markets; static list is deterministic |
| Data validation | `DataValidator` checks for stale/missing data | Prevents silent corruption from bad YFinance responses |
| Analysis caching | Cache LLM results to disk for backtest replay | Fast/cheap re-runs |
| Rate limiting | Configurable delay between API calls in batch mode | Prevents rate limit errors; enables cost awareness |
| CI | GitHub Actions | User preference |
| New code location | `tradingagents/portfolio/`, `tradingagents/backtest/`, `tradingagents/evaluation/` | Clean separation |

---

## Workflow Rules

1. Each ticket → feature branch → all tests pass → merge to main
2. Update `PLAN.md` after completing each ticket (mark done, add notes)
3. Never proceed to next ticket until current ticket's tests pass
4. Use `uv run pytest tests/` to verify before merging

---

## Progress Log

_Updated after each completed ticket._

| Ticket | Status | Branch | Notes |
|--------|--------|--------|-------|
| 1 | Not started | `feature/project-setup` | |
| 2 | Not started | `feature/analysis-horizon` | |
| 3 | Not started | `feature/stock-universe` | |
| 4 | Not started | `feature/batch-analysis` | |
| 5 | Not started | `feature/signal-scoring` | |
| 6 | Not started | `feature/portfolio-state` | |
| 7 | Not started | `feature/results-database` | Moved up from position 10 |
| 8 | Not started | `feature/position-sizing` | |
| 9 | Not started | `feature/portfolio-construction` | |
| 10 | Not started | `feature/rebalancing` | |
| 11 | Not started | `feature/backtesting` | |
| 12 | Not started | `feature/performance-metrics` | |
| 13 | Not started | `feature/prediction-consistency` | |
| 14 | Not started | `feature/model-comparison` | |
| 15 | Not started | `feature/portfolio-cli` | |
