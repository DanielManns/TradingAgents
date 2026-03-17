# Portfolio Management System - Implementation Plan

## Overview

Extend TradingAgents from single-stock BUY/HOLD/SELL recommendations into a full portfolio management system: 10-15 large-cap US equities, monthly rebalancing with transaction cost awareness, dual backtesting engines (custom loop + bt/ffn for cross-validation), and systematic evaluation of prediction quality.

**Phase 1 scope:** USD-denominated US large-cap equities only. Global markets (FX conversion, market calendars, timezone normalization) deferred to Phase 2.

**Principle — no fork:** The existing single-stock pipeline (`TradingAgentsGraph.propagate()`) stays untouched. New code wraps it at a higher level.

**Principle — minimal code:** Write only the least amount of custom code necessary. If a well-maintained Python library already implements a piece of functionality, use it instead of building from scratch. Glue code and thin wrappers are preferred over reimplementation. Every ticket should start by asking: "Is there a library that already does this?"

**Principle — cost awareness:** LLM calls at portfolio scale are expensive (~300+ calls per monthly rebalance). Every batch operation must support budget caps, analysis caching, and tiered screening to control costs.

**New packages:** `tradingagents/portfolio/`, `tradingagents/backtest/`, `tradingagents/evaluation/`, `tests/`

**Key libraries (new dependencies):**

| Library | Version | Purpose | Used in |
|---------|---------|---------|---------|
| `PyPortfolioOpt` | `>=1.5.6,<2.0` | Position sizing, weight constraints, sector caps, discrete allocation | Tickets 8, 9, 10 |
| `bt` + `ffn` | `bt>=1.1.3` | Second backtesting engine for cross-validation against custom loop | Ticket 11 |
| `pandera` | `>=0.20,<1.0` | DataFrame schema validation (stale prices, NaN, gaps) | Ticket 3 |
| `sqlite-utils` | `>=3.37,<4.0` | Zero-boilerplate SQLite (insert dicts, auto-schema, queries). Avoid v4.0 alpha (breaking upsert changes) | Ticket 7 |
| `instructor` | `>=1.7,<2.0` | Structured LLM output extraction with Pydantic validation + retries. Pin tightly — rapid release cadence | Ticket 5 |
| `quantstats-lumi` | `>=0.3.3,<0.4` | Performance metrics + HTML tearsheets. Actively maintained Lumiwealth fork (original `quantstats` is semi-abandoned) | Ticket 12 |

**Tooling:** `uv` for dependency resolution/installation (keep `setuptools` as build backend). `pytest` for testing. GitHub Actions for CI.

**Process:** Each ticket = feature branch → tests pass → merge to main. This plan file lives in the repo at `PLAN.md` and is updated after each ticket.

---

## Tickets (priority order)

### Ticket 1: Project Setup & Tooling — `feature/project-setup`
- **Depends on:** nothing (first ticket)
- [ ] **Add** `uv.lock` and update dev workflow to use `uv sync` / `uv run` (keep `setuptools` as build backend in `pyproject.toml`)
- [ ] **Remove** `backtrader>=1.9.78.123` from `pyproject.toml` (unmaintained since 2020, unused in codebase)
- [ ] **Remove** `redis>=6.2.0` from `pyproject.toml` (phantom dependency — declared but never imported anywhere in source)
- [ ] **Create** `tests/__init__.py`, `tests/conftest.py` with basic pytest setup
- [ ] **Modify** `pyproject.toml` — add `[tool.pytest.ini_options]`, add `pytest`, `pytest-mock` to `[project.optional-dependencies]` dev group
- [ ] **Create** `.github/workflows/ci.yml` — GitHub Actions: install with `uv`, run `pytest tests/`
- [ ] **AC:** `uv sync` installs all deps; `uv run pytest tests/` passes (empty suite); CI runs on push; backtrader and redis removed
- [ ] **Tests:** Verify pytest collection works
- [ ] **Note:** `rich`, `typer`, and CLI entry point already exist in `pyproject.toml` — no need to re-add

### Ticket 2: Configurable Analysis Time Horizon — `feature/analysis-horizon`
- **Depends on:** T1
- [ ] **Modify** `tradingagents/agents/analysts/fundamentals_analyst.py:22` — replace hardcoded "past week" with configurable `{analysis_period}` (default "past month")
- [ ] **Modify** `tradingagents/agents/analysts/news_analyst.py:19` — same: "past week" → `{analysis_period}`
- [ ] **Modify** `tradingagents/agents/analysts/social_media_analyst.py:19` — same: "past week" → `{analysis_period}`
- [ ] **Modify** `tradingagents/dataflows/yfinance_news.py:107` — change default `look_back_days` from 7 to 30
- [ ] **Modify** `tradingagents/dataflows/alpha_vantage_news.py:25` — change default `look_back_days` from 7 to 30
- [ ] **Modify** `tradingagents/default_config.py` — add `analysis_period` (default "past month"), `news_lookback_days` (default 30)
- [ ] **AC:** Running `propagate()` with default config uses "past month" in analyst prompts and 30-day news lookback
- [ ] **Tests:** Unit tests verify prompt interpolation and config propagation

### Ticket 3: Stock Universe & Screening — `feature/stock-universe`
- **Depends on:** T1 (pytest), T2 (config pattern)
- [ ] **Create** `tradingagents/portfolio/__init__.py`
- [ ] **Create** `tradingagents/portfolio/universe.py` — `StockUniverse` class: maintains a **static curated seed list** of ~50 US large-cap tickers as the primary source. Uses YFinance only to **validate and enrich** seed tickers (current market cap, sector, exchange) — not to discover new tickers. Support filtering by market cap and sector. Cache enriched data to `portfolio_data/universe.json`
- [ ] **Create** `tradingagents/portfolio/data_validation.py` — use **`pandera`** to define DataFrame schemas for YFinance data (price > 0, no NaN in close, monotonic date index, no gaps > 5 business days). Thin wrapper returning validation report with warnings. Used by universe screening and batch analysis
- [ ] **Modify** `tradingagents/default_config.py` — add `portfolio` config section: `min_market_cap` (default 50B for large-cap), `max_candidates`, `portfolio_data_dir`
- [ ] **AC:** `StockUniverse(config).get_candidates(30)` returns up to 30 validated US large-cap tickers with sector info; stale/missing data flagged
- [ ] **Tests:** Mock YFinance; verify filtering, caching, data validation
- [ ] **Note:** Phase 1 is USD-only. Global market support (FX conversion, market calendars via `exchange-calendars`, timezone normalization to UTC) deferred to Phase 2

### Ticket 4: Batch Analysis Orchestrator — `feature/batch-analysis`
- **Depends on:** T3 (ticker list from universe)
- [ ] **Create** `tradingagents/portfolio/batch_analyzer.py` — `BatchAnalyzer`: loops `propagate()` over ticker list, collects results, skips failures gracefully, supports progress callback. Includes **rate limiting** (configurable delay between API calls), **cost estimation** (log estimated LLM token usage per run), and **budget cap** (stop when estimated spend exceeds `max_batch_budget_usd`)
- [ ] **Modify** `tradingagents/graph/trading_graph.py` — add `reset_state(reset_memories=True)` method to clear `self.curr_state`, `self.ticker`, `self.log_states_dict` between runs. When `reset_memories=True` (default for batch mode), also reset `FinancialSituationMemory` instances (`bull_memory`, `bear_memory`, `trader_memory`, `invest_judge_memory`, `risk_manager_memory`) to prevent cross-contamination between ticker analyses
- [ ] **Create** `tradingagents/portfolio/analysis_cache.py` — `AnalysisCache`: caches LLM analysis results to disk (ticker+date → signal+state). Re-runs skip `propagate()` on cache hit. `cache_ttl_days` config (default 7) controls staleness. Shared by batch analysis (T4), rebalancing (T10), and backtesting (T11)
- [ ] **Modify** `tradingagents/default_config.py` — add `batch_delay_seconds` (default 1), `dry_run` (default False — skips LLM calls, returns mock results for pipeline testing), `max_batch_budget_usd` (default None — unlimited), `cache_ttl_days` (default 7)
- [ ] **AC:** Analyzes 3+ tickers; failures on one don't block others; results serializable to JSON; rate limiting respected; dry-run mode works without LLM calls; budget cap stops batch when exceeded; memories isolated between tickers; cache hits skip propagate()
- [ ] **Logging:** Configure Python `logging` with structured format (JSON or key=value). Create `tradingagents/portfolio/logging_config.py` with `setup_logging(level, log_dir)`. All portfolio-module code uses `logging.getLogger(__name__)`. `BatchAnalyzer` produces a run summary: tickers attempted, succeeded, failed (with error), cached, budget-stopped
- [ ] **Resume:** `BatchAnalyzer` writes a checkpoint file after each successful ticker analysis (list of completed tickers + results). On restart, skips already-completed tickers. Combined with analysis cache, this provides full resumability after crashes
- [ ] **Tests:** Mock `propagate()`; verify error isolation, result collection, progress callbacks, rate limiting, dry-run mode, budget cap, memory reset, cache hit/miss/expiry, checkpoint resume, run summary
- [ ] **Note:** Reflection (`reflect_and_remember()`) is NOT invoked during batch analysis — it requires known returns, which only exist during backtest rebalance cycles (T11) or after real-world price changes. Reflection is handled by T4.5

### Ticket 4.5: Memory Persistence & Portfolio-Level Reflection — `feature/memory-persistence`
- **Depends on:** T4 (batch analyzer), T6 (portfolio state for per-ticker returns)
- [ ] **Modify** `tradingagents/agents/utils/memory.py` — add `save(path)` and `load(path)` methods to `FinancialSituationMemory` (serialize `documents` and `recommendations` to JSON)
- [ ] **Create** `tradingagents/portfolio/reflection_manager.py` — `ReflectionManager`: after each rebalance cycle, computes per-ticker returns from portfolio snapshots, calls `reflect_and_remember()` for each holding that was sold or rebalanced, then saves memories to `portfolio_data/memories/`. On next cycle, loads persisted memories before analysis
- [ ] **Modify** `tradingagents/default_config.py` — add `enable_reflection` (default True), `memory_persistence_dir` (default `portfolio_data/memories/`)
- [ ] **AC:** Memories survive process restart; reflection runs after each backtest month and after live rebalances; memories are ticker-isolated during batch but accumulated across rebalance cycles
- [ ] **Tests:** Round-trip save/load of `FinancialSituationMemory`; reflection integration with mock returns; verify memories accumulate across cycles but don't cross-contaminate within a batch

### Ticket 5: Signal Scoring & Ranking — `feature/signal-scoring`
- **Depends on:** T4 (batch results to score)
- [ ] **Create** `tradingagents/portfolio/scoring.py` — `SignalScorer`: uses **`instructor`** with a Pydantic model to extract structured conviction score (-1.0 to +1.0) + signal enum (BUY/HOLD/SELL) from `final_trade_decision` text. `instructor` handles retries on validation failure. `rank_candidates()` sorts by conviction. Keyword fallback if LLM fails (BUY=0.5, HOLD=0.0, SELL=-0.5). **Clamp** scores outside [-1, 1] via Pydantic validator. Log and flag low-confidence or ambiguous extractions (e.g., "cautious buy", "weak hold") for review
- [ ] **AC:** Strong BUY > 0.5, strong SELL < -0.5, HOLD near 0; ranking correct; out-of-range scores clamped; ambiguous signals logged
- [ ] **Tests:** Mock LLM; test with known signal texts; verify fallback logic; verify clamping; test ambiguous signal handling
- [ ] **Note:** `SignalScorer` operates externally on batch results — it does NOT replace the existing `SignalProcessor` inside `TradingAgentsGraph`. `SignalProcessor` remains for single-stock CLI usage (backward compatible). Phase 2: optionally replace `SignalProcessor` with `SignalScorer` inside the graph to avoid double LLM extraction

### Ticket 6: Portfolio State Management — `feature/portfolio-state`
- **Depends on:** T1 (config pattern); independent of T4-T5
- [ ] **Create** `tradingagents/portfolio/models.py` — dataclasses: `Position`, `Transaction`, `PortfolioSnapshot`, `PortfolioState`
- [ ] **Create** `tradingagents/portfolio/state_manager.py` — `PortfolioStateManager`: init, load, save, record transactions, take snapshots, validate (no selling unheld shares, no overspending cash). JSON persistence in `portfolio_data/` (DB migration planned later)
- [ ] **Create** `tradingagents/portfolio/config_schema.py` — Pydantic model for portfolio config section. Validates types, ranges (e.g., `0 < max_position_pct <= 1`, `starting_cash > 0`, `transaction_cost_bps >= 0`), and required fields. Called at portfolio init time. Raises clear errors on invalid config (prevents silent misconfiguration across the ~20 config keys added by T2-T12)
- [ ] **Add** `PortfolioStateManager.get_value_series()` — returns a pandas Series of portfolio values over time (from stored snapshots). `get_holdings_series()` returns per-ticker value time series. These feed directly into quantstats-lumi (T12)
- [ ] **Add** CLI subcommands `portfolio status` (current holdings, P&L, allocation as Rich table) and `portfolio history` (transaction history) to `cli/portfolio_commands.py`. Register as subcommand group in `cli/main.py`
- [ ] **Modify** `tradingagents/default_config.py` — add `starting_cash` (default 1_000_000), `transaction_cost_bps` (default 10)
- [ ] **AC:** CRUD round-trips via JSON; rejects invalid transactions; snapshots with current prices; value series aggregated from snapshots; config validation catches invalid values; CLI status/history commands work
- [ ] **Tests:** Full state lifecycle tests; edge cases (overdraw, short sell rejection); config validation rejects bad values; value series computation

### Ticket 7: Analysis Results Database — `feature/results-database`
- **Depends on:** T1; independent of T4-T6
- [ ] **Create** `tradingagents/portfolio/database.py` — `AnalysisDatabase` using **`sqlite-utils`** (pin `>=3.37,<4.0`): stores analysis results (ticker, date, signal, conviction score, full state JSON, model used, estimated cost, timestamp) in SQLite. Query by ticker, date range, model. Replaces/supplements `eval_results/` JSON logging
- [ ] **Modify** `tradingagents/graph/trading_graph.py` — optionally write to DB after each `propagate()` call
- [ ] **Add** `AnalysisDatabase.cleanup(older_than_days=90)` — removes analysis results older than threshold. `AnalysisCache.purge_expired()` (from T4) physically deletes expired cache entries. Prevents unbounded storage growth
- [ ] **AC:** Analysis results persist across runs; queryable by ticker+date+model; existing JSON logging still works; cleanup removes old records
- [ ] **Tests:** CRUD operations, query filters, schema migration, cleanup respects age threshold
- [ ] **Note:** Moved earlier (was Ticket 10) because Tickets 11, 13, 14 depend on it, and portfolio construction benefits from queryable storage from the start

### Ticket 8: Position Sizing & Constraints — `feature/position-sizing`
- **Depends on:** T5 (scored candidates), T6 (portfolio state)
- [ ] **Create** `tradingagents/portfolio/price_service.py` — `PriceService`: thin wrapper around YFinance that fetches close prices for a list of tickers on a given date, with disk caching. Used by position sizing (T8), portfolio construction (T9), rebalancing (T10), backtesting (T11), and snapshots. Extracted early because discrete allocation and transaction recording both require actual prices
- [ ] **Create** `tradingagents/portfolio/position_sizing.py` — `EqualWeightSizer` (default). Base class `PositionSizer` for future strategies (e.g., `PyPortfolioOpt`-backed MVO sizer). Accepts ranked stocks + portfolio state, returns target allocations. Use `PyPortfolioOpt.DiscreteAllocation` to convert continuous weights to integer share counts (requires prices from `PriceService`)
- [ ] **Create** `tradingagents/portfolio/constraints.py` — `PortfolioConstraints`: max stocks per sector, min sectors, max single-stock weight; `validate_portfolio()` reports violations. Optional (None = disabled)
- [ ] **Modify** `tradingagents/default_config.py` — add `target_num_holdings` (12), `max_position_pct` (0.10), `max_stocks_per_sector` (3), `min_sectors` (4)
- [ ] **AC:** 12 stocks with $1M → ~$83K each; sector caps enforced; constraints optional; discrete share counts computed using real prices; price service caches to disk
- [ ] **Tests:** Sizing math; constraint enforcement; edge cases (fewer candidates than target); discrete allocation rounding; price service caching

### Ticket 9: Portfolio Construction — `feature/portfolio-construction`
- **Depends on:** T5, T6, T7, T8 (all upstream components)
- [ ] **Create** `tradingagents/portfolio/constructor.py` — `PortfolioConstructor.build_initial_portfolio(date, config)`: orchestrates universe screening → data validation → batch analysis (with cache) → scoring → constraints → sizing → transactions → snapshot. Stores analysis results in DB (Ticket 7). Uses analysis cache (Ticket 4) to avoid redundant LLM calls
- [ ] **Add** CLI subcommands `portfolio init` (initialize universe, starting cash, constraints) and `portfolio build --date YYYY-MM-DD` (run initial construction) to `cli/portfolio_commands.py`
- [ ] **AC:** Given a date and config, produces a portfolio of 10-15 stocks with full audit trail; data validation warnings surfaced; analysis results cached and stored in DB; CLI init+build commands work end-to-end
- [ ] **Tests:** Integration test with all components mocked at boundaries; CLI invocation tests

### Ticket 10: Monthly Rebalancing with Transaction Cost Awareness — `feature/rebalancing`
- **Depends on:** T9 (portfolio construction)
- [ ] **Create** `tradingagents/portfolio/rebalancer.py` — `PortfolioRebalancer.rebalance(portfolio, date, config)`:
  1. Re-analyze current holdings (use `quick_think_llm` for retention checks — cheaper than full pipeline) + screen new candidates
  2. Score all together; use analysis cache (T4) to skip recent analyses within `cache_ttl_days`
  3. **Transaction cost hurdle:** only replace if score improvement > `min_score_improvement` (default 0.15)
  4. `max_turnover_pct` (default 0.30) caps changes per rebalance
  5. Sells before buys to free cash; transaction costs deducted
  6. **Drift trigger:** `check_drift(portfolio)` returns True if any position drifts > `drift_threshold_pct` from target weight — can trigger ad-hoc rebalance between monthly cycles
  7. **Idempotent:** re-running rebalance on same date with no drift produces no transactions
- [ ] **Modify** `tradingagents/default_config.py` — add `min_score_improvement` (default 0.15), `max_turnover_pct` (default 0.30), `drift_threshold_pct` (default 0.05)
- [ ] **Add** CLI subcommand `portfolio rebalance --date YYYY-MM-DD` to `cli/portfolio_commands.py`
- [ ] **AC:** Holding at 0.6 NOT replaced by candidate at 0.7 (gap < 0.15); holding at 0.3 IS replaced by candidate at 0.8 (gap > 0.15); turnover capped; drift detection works; idempotent on re-run; CLI rebalance command works
- [ ] **Tests:** Test hurdle logic, turnover cap, sell-before-buy ordering, cost deduction, drift detection, idempotency
- [ ] **Note:** Drift alerting (email, webhook) deferred to Phase 2

### Ticket 11: Backtesting Engine (Dual: Custom + bt/ffn) — `feature/backtesting`
- **Depends on:** T9 (portfolio construction), T10 (rebalancing)
- [ ] **Create** `tradingagents/backtest/__init__.py`
- [ ] **Create** `tradingagents/backtest/data_feeds.py` — YFinance historical price adapter: fetches OHLCV for date ranges, caches to disk. Shared by both engines
- [ ] **Create** `tradingagents/backtest/custom_engine.py` — `CustomBacktestEngine.run(start_date, end_date, config)`: lightweight month-by-month loop using `PortfolioConstructor` then `PortfolioRebalancer`. Replays monthly snapshots with price lookups. Full control over transaction logic and cost modeling. Uses shared analysis cache (T4) — second run skips `propagate()` on cache hit
- [ ] **Create** `tradingagents/backtest/bt_engine.py` — `BtBacktestEngine.run(start_date, end_date, config)`: uses **`bt`+`ffn`** algo-tree architecture. Takes the same pre-computed monthly signals (from analysis cache) and replays them using `bt.Algo` pipeline (`RunMonthly` → `SelectThese` → `WeighTarget` → `Rebalance`). Produces bt's built-in stats and analytics. Purpose: cross-validate the custom engine's results — if both agree, confidence in the backtest is high
- [ ] **Create** `tradingagents/backtest/comparison.py` — `BacktestComparator`: runs both engines on the same date range, compares portfolio values, returns, and key metrics. Flags discrepancies > threshold (default 1% cumulative return difference). Generates comparison report
- [ ] **Modify** `tradingagents/default_config.py` — add `backtest` section with `engine` (default "both" | "custom" | "bt"), `comparison_threshold_pct` (default 1.0)
- [ ] **Add** CLI subcommand `portfolio backtest --start --end --engine [both|custom|bt]` to `cli/portfolio_commands.py` — progress bar + metrics + engine comparison
- [ ] **Create** `tests/integration/test_backtest_e2e.py` — end-to-end test using recorded/mocked LLM responses for 3 tickers over 2 months. Validates full flow: universe → batch analysis → scoring → construction → rebalance → metrics. Uses `dry_run` mode
- [ ] **AC:** 12-month backtest produces monthly portfolio values from both engines; second run uses cache (no LLM calls); comparison report shows agreement/discrepancy; engines can be run independently or together; CLI backtest command works with progress bar
- [ ] **Tests:** Test both engines with synthetic data; verify caching; verify month-by-month progression; verify comparison detects intentional discrepancies; e2e integration test passes
- [ ] **Note:** `backtrader` removed in T1 (unmaintained since 2020). `bt`+`ffn` (actively maintained, last release Feb 2026) used as the second engine for validation, not as the primary

### Ticket 12: Performance Metrics — `feature/performance-metrics`
- **Depends on:** T11 (portfolio value series from backtest)
- [ ] **Add** `quantstats-lumi>=0.3.3,<0.4` as dependency (actively maintained Lumiwealth fork — Sharpe, Sortino, max drawdown, alpha/beta, 40+ metrics, HTML tearsheet). Fallback: `empyrical` if quantstats-lumi proves problematic
- [ ] **Create** `tradingagents/portfolio/metrics.py` — thin wrapper around `quantstats-lumi`: `compute_metrics(portfolio_values, benchmark="SPY")` returns metrics dict; `generate_report(output_path)` creates HTML tearsheet
- [ ] **Create** `tradingagents/portfolio/benchmark.py` — `BenchmarkProvider`: fetches SPY or configurable benchmark via YFinance
- [ ] **(Optional)** `compute_attribution(holdings_series, benchmark)` — decomposes portfolio return into per-ticker contributions (simple weight × return decomposition). Answers "which stocks helped/hurt most?"
- [ ] **AC:** Metrics match QuantStats output for known inputs; HTML report generated; attribution (if implemented) correctly decomposes returns
- [ ] **Tests:** Verify wrapper with synthetic return series; verify attribution sums to total return

### Ticket 13: Prediction Consistency Evaluation — `feature/prediction-consistency`
- **Depends on:** T7 (DB for storing results), T5 (signal scoring)
- [ ] **Create** `tradingagents/evaluation/__init__.py`
- [ ] **Create** `tradingagents/evaluation/consistency.py` — `ConsistencyEvaluator`: runs the same analysis N times for a given ticker+date with the same model/data, measures agreement rate (% of runs with same BUY/HOLD/SELL), score variance, and confidence intervals. Stores results in DB (Ticket 7). **Cost warning:** N=5 means 5× full pipeline cost per ticker — log estimated cost before running and respect `max_batch_budget_usd`
- [ ] **AC:** For a given ticker+date, running 5 analyses shows agreement rate and score distribution
- [ ] **Tests:** Mock propagate with deterministic and varied outputs; verify stats calculations

### Ticket 14: Cross-Model Comparison — `feature/model-comparison`
- **Depends on:** T7 (DB), T5 (signal scoring)
- [ ] **Create** `tradingagents/evaluation/model_comparison.py` — `ModelComparator`: runs the same ticker+date analysis across multiple LLM configurations (e.g., GPT-4o, Claude, Gemini), compares signals, scores, and reasoning. Generates comparison report. Uses DB (Ticket 7) to store/retrieve results per model
- [ ] **Add** CLI subcommand `portfolio evaluate --ticker --date` to `cli/portfolio_commands.py` — runs consistency eval (T13) and/or model comparison (T14) based on flags
- [ ] **AC:** Compare 2+ models on same ticker+date; report shows agreement/disagreement, score deltas, reasoning diffs; CLI evaluate command works
- [ ] **Tests:** Mock multiple model configs; verify comparison logic and report generation

### Ticket 15: CLI Polish & Cost Tooling — `feature/portfolio-cli`
- **Depends on:** T1-T14 (all CLI subcommands already added incrementally in T6, T9, T10, T11, T14)
- [ ] **Add** `portfolio cost-estimate --tickers N` — estimate LLM cost for a batch run without executing (uses dry-run mode to calculate expected calls × model pricing)
- [ ] **Polish** Rich output consistency across all portfolio subcommands — unified table styles, color coding, progress bar patterns
- [ ] **Add** `portfolio report --output PATH` — generate combined HTML report: portfolio status + performance metrics + backtest comparison (aggregates outputs from T6, T12, T11)
- [ ] **Verify** all subcommands registered correctly in `cli/main.py` subcommand group; no conflicts with existing single-stock `analyze` command
- [ ] **AC:** All portfolio commands work end-to-end with consistent Rich output; cost-estimate provides accurate projection; combined report generates
- [ ] **Tests:** Full CLI integration tests across all subcommands with mocked backends
- [ ] **Note:** Individual CLI commands were added incrementally: `status`/`history` in T6, `init`/`build` in T9, `rebalance` in T10, `backtest` in T11, `evaluate` in T14. This ticket is polish + cost tooling only

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Build backend | `setuptools` (unchanged) | `uv` is a package manager, not a build backend — keep them separate. `uv_build` available since July 2025 as alternative; revisit if setuptools causes friction |
| Dependency mgmt | `uv` for resolution/installation | Fast, reliable, user preference |
| Storage (phase 1) | JSON files in `portfolio_data/` | Simple start; matches existing patterns |
| Storage (phase 2) | SQLite via `sqlite-utils` for analysis results (Ticket 7) | Queryable, persistent, no server needed; introduced early so downstream tickets build on it. Pin to v3.x (v4.0 alpha has breaking changes) |
| Cache storage | Disk files + SQLite | Redis removed (was unused phantom dependency). Can be reintroduced if multi-process/distributed caching is needed |
| Performance metrics | `quantstats-lumi` (Lumiwealth fork), fallback: `empyrical` | 40+ metrics, HTML tearsheets — minimal custom code. Original `quantstats` is semi-abandoned; Lumiwealth fork actively maintained |
| Backtesting | Dual engines: custom replay loop + `bt`/`ffn` | Custom loop gives full control over transaction logic; `bt`/`ffn` (actively maintained, Feb 2026) provides independent cross-validation. Compare results to build confidence. `backtrader` removed (unmaintained since 2020) |
| Scoring | LLM extracts conviction float via `instructor` + Pydantic | Structured extraction with validation + retries. Keyword fallback if LLM fails. Scores clamped to [-1, 1]. Pin `instructor` tightly (rapid release cadence) |
| Core pipeline | Unchanged (except configurable time horizon) | New code calls `propagate()`, never forks it |
| Position sizing | Equal weight (default), pluggable via `PyPortfolioOpt` | User preference; extensible to MVO, HRP. `Riskfolio-Lib` as future alternative for advanced risk models |
| Market scope | Phase 1: USD-denominated US large-cap equities | FX conversion, market calendars (`exchange-calendars`), timezone normalization deferred to Phase 2 |
| Universe | Static curated US large-cap seed list (~50 tickers); YFinance for validation/enrichment only | Static list is deterministic; YFinance screener unreliable |
| Data validation | `pandera` DataFrame schemas for stale/missing data | Prevents silent corruption from bad YFinance responses |
| Analysis caching | Shared `AnalysisCache` in `tradingagents/portfolio/` with configurable TTL | Used by batch analysis (T4), rebalancing (T10), and backtesting (T11). Cache TTL prevents stale results |
| LLM cost controls | Budget caps, analysis caching, cheaper model for re-analysis | ~300+ LLM calls per monthly rebalance at scale. `max_batch_budget_usd` stops batch when exceeded. Retention checks use `quick_think_llm` |
| Memory isolation | Reset `FinancialSituationMemory` between batch runs | Prevents cross-contamination of analyst reasoning across ticker analyses |
| Rebalancing triggers | Calendar (monthly) + drift threshold (>5% position drift) | Best practice: combine time-based and drift-based triggers. Idempotent operations |
| Rate limiting | Configurable delay between API calls in batch mode | Prevents rate limit errors; enables cost awareness |
| Version pinning | Pin `instructor`, `sqlite-utils`, `quantstats-lumi` to minor versions | These libraries have rapid releases or breaking change risk between minors |
| Memory persistence | Serialize `FinancialSituationMemory` to JSON; reload on next cycle | Learning accumulates across rebalance cycles; survives process restart. Without this, all reflection is lost between runs |
| Dividends / corporate actions | Phase 1 uses adjusted close prices (splits handled by YFinance). Dividend reinvestment deferred to Phase 2 | Sufficient for monthly rebalancing of large-cap equities. Dividend impact is secondary for backtesting accuracy |
| Drift alerting | Phase 1: CLI-only (`portfolio status` shows drift). Phase 2: email/webhook notifications | CLI-first tool; scheduled alerting adds infrastructure complexity |
| SignalProcessor vs SignalScorer | Both coexist. `SignalProcessor` for single-stock CLI; `SignalScorer` for portfolio batch. Phase 2: unify | Backward compatible; avoids modifying core pipeline. Unification deferred to reduce risk |
| Price service | Shared `PriceService` with disk caching, introduced in T8 | Needed by T8 (discrete allocation), T9 (construction), T10 (rebalancing), T11 (backtesting). Too fundamental to defer to T11 |
| CLI distribution | CLI subcommands added incrementally with their feature tickets, not batched at the end | Reduces integration risk; each feature is testable end-to-end when delivered |
| CI | GitHub Actions | User preference |
| New code location | `tradingagents/portfolio/`, `tradingagents/backtest/`, `tradingagents/evaluation/` | Clean separation |

---

## Ticket Dependency Graph

```
T1 (Setup)
 ├─→ T2 (Time Horizon) ─→ T3 (Universe) ─→ T4 (Batch + Cache + Logging)
 │                                                │
 │                                           T4.5 (Memory Persistence) ←─┐
 │                                                │                       │
 │                                           T5 (Scoring)                 │
 ├─→ T6 (Portfolio State + Config Schema + CLI: status/history) ─────────┐│
 └─→ T7 (Database + Cleanup) ──────────────────────────────────────────┐││
                                                                        │││
     T5 + T6 ─→ T8 (Position Sizing + Price Service) ─────────────────┐│││
                                                                       ││││
     T5 + T6 + T7 + T8 ─→ T9 (Construction + CLI: init/build) ◄──────┘│││
                                │                                       │││
                          T10 (Rebalancing + CLI: rebalance) ◄──────────┘││
                                │                                        ││
                          T11 (Backtesting: dual + CLI + e2e tests)      ││
                                │                                        ││
                          T12 (Metrics + Attribution)                     ││
                                                                         ││
     T7 + T5 ─→ T13 (Consistency Eval) ◄────────────────────────────────┘│
     T7 + T5 ─→ T14 (Model Comparison + CLI: evaluate) ◄─────────────────┘

     T1-T14 ─→ T15 (CLI Polish + Cost Tooling)
```

**Parallelizable:** T6 and T7 can be developed in parallel with T4-T5 (independent data structures). T13 and T14 can start after T7 (do not depend on T11-T12). T4.5 depends on T4 + T6 but can overlap with T5.

**CLI distribution:** Subcommands added incrementally — `status`/`history` in T6, `init`/`build` in T9, `rebalance` in T10, `backtest` in T11, `evaluate` in T14. T15 is polish + cost-estimate only.

---

## Workflow Rules

### Definition of Done (per ticket)

A ticket can only be marked as done when **all** of the following are satisfied:

1. **Unit tests pass** — `uv run pytest tests/` passes with all new and existing tests green
2. **CI pipeline green** — GitHub Actions CI workflow completes successfully on the feature branch (lint, test, build)
3. **Code quality adherence** — code follows project quality principles:
   - No linting errors or warnings
   - Type hints on all new public functions and methods
   - No security vulnerabilities (OWASP top 10, no hardcoded secrets)
   - No dead code or unused imports
   - Functions and classes have clear single responsibilities
   - Error handling at system boundaries (user input, external APIs)
4. **Code review** — use the code-reviewer agent on all changed files before merging
5. **Plan updated** — mark the ticket as done in the Progress Log below and add notes

### Process

1. Each ticket → feature branch → tests pass → CI green → code review → merge to main
2. Never proceed to next ticket until current ticket satisfies the Definition of Done
3. If CI fails, fix the issue and re-push — do not bypass or skip checks

---

## Progress Log

_Updated after each completed ticket._

| Ticket | Status | Branch | Depends on | Notes |
|--------|--------|--------|------------|-------|
| 1 | Not started | `feature/project-setup` | — | Remove backtrader + redis |
| 2 | Not started | `feature/analysis-horizon` | T1 | |
| 3 | Not started | `feature/stock-universe` | T1, T2 | USD-only Phase 1 |
| 4 | Not started | `feature/batch-analysis` | T3 | Includes analysis cache, budget cap, memory reset, logging, checkpoint resume |
| 4.5 | Not started | `feature/memory-persistence` | T4, T6 | Memory save/load + portfolio-level reflection |
| 5 | Not started | `feature/signal-scoring` | T4 | SignalScorer coexists with existing SignalProcessor |
| 6 | Not started | `feature/portfolio-state` | T1 | Parallelizable with T4-T5; includes config schema + CLI status/history |
| 7 | Not started | `feature/results-database` | T1 | Parallelizable with T4-T6; includes cleanup; moved up from position 10 |
| 8 | Not started | `feature/position-sizing` | T5, T6 | Includes PriceService (shared by T9-T11) |
| 9 | Not started | `feature/portfolio-construction` | T5, T6, T7, T8 | Includes CLI init/build |
| 10 | Not started | `feature/rebalancing` | T9 | Drift-based + calendar triggers; includes CLI rebalance |
| 11 | Not started | `feature/backtesting` | T9, T10 | Dual engines: custom + bt/ffn; includes CLI backtest + e2e integration test |
| 12 | Not started | `feature/performance-metrics` | T11 | Uses quantstats-lumi; optional attribution |
| 13 | Not started | `feature/prediction-consistency` | T7, T5 | Can start after T7 (independent of T11-T12) |
| 14 | Not started | `feature/model-comparison` | T7, T5 | Can start after T7; includes CLI evaluate |
| 15 | Not started | `feature/portfolio-cli` | T1-T14 | Polish + cost-estimate + combined report only (subcommands distributed to feature tickets) |
