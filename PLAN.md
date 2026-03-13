# Portfolio Management System - Implementation Plan

## Overview

Extend TradingAgents from single-stock BUY/HOLD/SELL recommendations into a full portfolio management system: 10-15 large-cap stocks from global developed markets, monthly rebalancing with transaction cost awareness, backtesting, and systematic evaluation of prediction quality.

**Principle:** The existing single-stock pipeline (`TradingAgentsGraph.propagate()`) stays untouched. New code wraps it at a higher level.

**New packages:** `tradingagents/portfolio/`, `tradingagents/backtest/`, `tradingagents/evaluation/`, `tests/`

**Tooling:** `uv` for dependency management. `pytest` for testing. GitHub Actions for CI.

**Process:** Each ticket = feature branch → tests pass → merge to main. This plan file lives in the repo at `PLAN.md` and is updated after each ticket.

---

## Tickets (priority order)

### Ticket 1: Project Setup & Tooling — `feature/project-setup`
- [ ] **Migrate** to `uv` for dependency management (add `uv.lock`, update dev workflow)
- [ ] **Create** `tests/__init__.py`, `tests/conftest.py` with basic pytest setup
- [ ] **Modify** `pyproject.toml` — add `[tool.pytest.ini_options]`, add `pytest`, `pytest-mock` to dev deps
- [ ] **Create** `.github/workflows/ci.yml` — GitHub Actions: install with `uv`, run `pytest tests/`
- [ ] **AC:** `uv sync` installs all deps; `uv run pytest tests/` passes (empty suite); CI runs on push
- [ ] **Tests:** Verify pytest collection works

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
- [ ] **Create** `tradingagents/portfolio/universe.py` — `StockUniverse` class: uses YFinance to screen stocks by market cap across global developed markets (US, Europe, Japan, UK, etc.). Start with a small curated seed list of ~50 large-cap tickers from major exchanges as the initial universe. Support filtering by market cap, sector, exchange. Cache to `portfolio_data/universe.json`
- [ ] **Modify** `tradingagents/default_config.py` — add `portfolio` config section: `min_market_cap` (default 50B for large-cap), `max_candidates`, `portfolio_data_dir`
- [ ] **AC:** `StockUniverse(config).get_candidates(30)` returns up to 30 tickers with sector/exchange info from global markets
- [ ] **Tests:** Mock YFinance; verify filtering, caching, global market coverage

### Ticket 4: Batch Analysis Orchestrator — `feature/batch-analysis`
- [ ] **Create** `tradingagents/portfolio/batch_analyzer.py` — `BatchAnalyzer`: loops `propagate()` over ticker list, collects results, skips failures gracefully, supports progress callback
- [ ] **Modify** `tradingagents/graph/trading_graph.py` — add `reset_state()` method to clear `self.curr_state`, `self.ticker`, `self.log_states_dict` between runs
- [ ] **AC:** Analyzes 3+ tickers; failures on one don't block others; results serializable to JSON
- [ ] **Tests:** Mock `propagate()`; verify error isolation, result collection, progress callbacks

### Ticket 5: Signal Scoring & Ranking — `feature/signal-scoring`
- [ ] **Create** `tradingagents/portfolio/scoring.py` — `SignalScorer`: extracts numeric conviction score (-1.0 to +1.0) from `final_trade_decision` text using LLM (same pattern as `SignalProcessor` in `tradingagents/graph/signal_processing.py`); `rank_candidates()` sorts by conviction. Keyword fallback if LLM fails (BUY=0.5, HOLD=0.0, SELL=-0.5)
- [ ] **AC:** Strong BUY > 0.5, strong SELL < -0.5, HOLD near 0; ranking correct
- [ ] **Tests:** Mock LLM; test with known signal texts; verify fallback logic

### Ticket 6: Portfolio State Management — `feature/portfolio-state`
- [ ] **Create** `tradingagents/portfolio/models.py` — dataclasses: `Position`, `Transaction`, `PortfolioSnapshot`, `PortfolioState`
- [ ] **Create** `tradingagents/portfolio/state_manager.py` — `PortfolioStateManager`: init, load, save, record transactions, take snapshots, validate (no selling unheld shares, no overspending cash). JSON persistence in `portfolio_data/` (DB migration planned later)
- [ ] **Modify** `tradingagents/default_config.py` — add `starting_cash` (default 1_000_000), `transaction_cost_bps` (default 10)
- [ ] **AC:** CRUD round-trips via JSON; rejects invalid transactions; snapshots with current prices
- [ ] **Tests:** Full state lifecycle tests; edge cases (overdraw, short sell rejection)

### Ticket 7: Position Sizing & Constraints — `feature/position-sizing`
- [ ] **Create** `tradingagents/portfolio/position_sizing.py` — `EqualWeightSizer` (default). Base class `PositionSizer` for future strategies. Accepts ranked stocks + portfolio state, returns target allocations
- [ ] **Create** `tradingagents/portfolio/constraints.py` — `PortfolioConstraints`: max stocks per sector, min sectors, max single-stock weight; `validate_portfolio()` reports violations. Optional (None = disabled)
- [ ] **Modify** `tradingagents/default_config.py` — add `target_num_holdings` (12), `max_position_pct` (0.10), `max_stocks_per_sector` (3), `min_sectors` (4)
- [ ] **AC:** 12 stocks with $1M → ~$83K each; sector caps enforced; constraints optional
- [ ] **Tests:** Sizing math; constraint enforcement; edge cases (fewer candidates than target)

### Ticket 8: Portfolio Construction — `feature/portfolio-construction`
- [ ] **Create** `tradingagents/portfolio/constructor.py` — `PortfolioConstructor.build_initial_portfolio(date, config)`: orchestrates universe screening → batch analysis → scoring → constraints → sizing → transactions → snapshot
- [ ] **AC:** Given a date and config, produces a portfolio of 10-15 stocks with full audit trail
- [ ] **Tests:** Integration test with all components mocked at boundaries

### Ticket 9: Monthly Rebalancing with Transaction Cost Awareness — `feature/rebalancing`
- [ ] **Create** `tradingagents/portfolio/rebalancer.py` — `PortfolioRebalancer.rebalance(portfolio, date, config)`:
  1. Re-analyze current holdings + screen new candidates
  2. Score all together
  3. **Transaction cost hurdle:** only replace if score improvement > `min_score_improvement` (default 0.3)
  4. `max_turnover_pct` (default 0.30) caps changes per rebalance
  5. Sells before buys to free cash; transaction costs deducted
- [ ] **Modify** `tradingagents/default_config.py` — add `min_score_improvement`, `max_turnover_pct`
- [ ] **AC:** Holding at 0.6 NOT replaced by candidate at 0.7 (gap < 0.3); stock at -0.3 IS replaced; turnover capped
- [ ] **Tests:** Test hurdle logic, turnover cap, sell-before-buy ordering, cost deduction

### Ticket 10: Analysis Results Database — `feature/results-database`
- [ ] **Research** best lightweight DB for this use case (SQLite via `sqlite3` stdlib likely sufficient)
- [ ] **Create** `tradingagents/portfolio/database.py` — `AnalysisDatabase`: stores analysis results (ticker, date, signal, conviction score, full state JSON, model used, timestamp) in SQLite. Query by ticker, date range, model. Replaces/supplements `eval_results/` JSON logging
- [ ] **Modify** `tradingagents/graph/trading_graph.py` — optionally write to DB after each `propagate()` call
- [ ] **AC:** Analysis results persist across runs; queryable by ticker+date+model; existing JSON logging still works
- [ ] **Tests:** CRUD operations, query filters, schema migration

### Ticket 11: Backtesting Engine — `feature/backtesting`
- [ ] **Create** `tradingagents/backtest/__init__.py`
- [ ] **Create** `tradingagents/backtest/engine.py` — `BacktestEngine.run(start_date, end_date, config)`: month-by-month loop using `PortfolioConstructor` then `PortfolioRebalancer`; uses `backtrader` for execution simulation
- [ ] **Create** `tradingagents/backtest/data_feeds.py` — YFinance → `bt.feeds.PandasData` adapter
- [ ] **Create** `tradingagents/backtest/strategy.py` — `backtrader.Strategy` subclass executing pre-computed orders
- [ ] **Create** `tradingagents/backtest/analysis_cache.py` — caches LLM analysis results to disk (ticker+date → signal). Re-runs skip `propagate()` on cache hit. Essential for fast iteration
- [ ] **Modify** `tradingagents/default_config.py` — add `backtest` section with `cache_analyses` (default True)
- [ ] **AC:** 12-month backtest produces daily portfolio values; second run uses cache (no LLM calls)
- [ ] **Tests:** Test with synthetic data; verify caching; verify month-by-month progression

### Ticket 12: Performance Metrics (via QuantStats) — `feature/performance-metrics`
- [ ] **Add** `quantstats` as dependency (comprehensive metrics library: Sharpe, Sortino, max drawdown, alpha/beta, 40+ metrics, HTML tearsheet generation)
- [ ] **Create** `tradingagents/portfolio/metrics.py` — thin wrapper around `quantstats`: `compute_metrics(portfolio_values, benchmark="SPY")` returns metrics dict; `generate_report(output_path)` creates HTML tearsheet
- [ ] **Create** `tradingagents/portfolio/benchmark.py` — `BenchmarkProvider`: fetches SPY or configurable benchmark via YFinance
- [ ] **AC:** Metrics match QuantStats output for known inputs; HTML report generated
- [ ] **Tests:** Verify wrapper with synthetic return series

### Ticket 13: Prediction Consistency Evaluation — `feature/prediction-consistency`
- [ ] **Create** `tradingagents/evaluation/__init__.py`
- [ ] **Create** `tradingagents/evaluation/consistency.py` — `ConsistencyEvaluator`: runs the same analysis N times for a given ticker+date with the same model/data, measures agreement rate (% of runs with same BUY/HOLD/SELL), score variance, and confidence intervals. Stores results in DB (Ticket 10)
- [ ] **AC:** For a given ticker+date, running 5 analyses shows agreement rate and score distribution
- [ ] **Tests:** Mock propagate with deterministic and varied outputs; verify stats calculations

### Ticket 14: Cross-Model Comparison — `feature/model-comparison`
- [ ] **Create** `tradingagents/evaluation/model_comparison.py` — `ModelComparator`: runs the same ticker+date analysis across multiple LLM configurations (e.g., GPT-4o, Claude, Gemini), compares signals, scores, and reasoning. Generates comparison report. Uses DB (Ticket 10) to store/retrieve results per model
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
| Storage (phase 1) | JSON files in `portfolio_data/` | Simple start; matches existing patterns |
| Storage (phase 2) | SQLite for analysis results (Ticket 10) | Queryable, persistent, no server needed |
| Performance metrics | QuantStats library | 40+ metrics, HTML tearsheets, actively maintained — minimal custom code |
| Scoring | LLM extracts conviction float from `final_trade_decision` | Reuses `SignalProcessor` pattern; no pipeline modification |
| Core pipeline | Unchanged (except configurable time horizon) | New code calls `propagate()`, never forks it |
| Position sizing | Equal weight (default), pluggable | User preference; extensible later |
| Universe | Small curated global large-cap seed list, expandable | Start small, extend easily |
| Analysis caching | Cache LLM results to disk for backtest replay | Fast/cheap re-runs |
| Dependency mgmt | `uv` | User preference |
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
| 7 | Not started | `feature/position-sizing` | |
| 8 | Not started | `feature/portfolio-construction` | |
| 9 | Not started | `feature/rebalancing` | |
| 10 | Not started | `feature/results-database` | |
| 11 | Not started | `feature/backtesting` | |
| 12 | Not started | `feature/performance-metrics` | |
| 13 | Not started | `feature/prediction-consistency` | |
| 14 | Not started | `feature/model-comparison` | |
| 15 | Not started | `feature/portfolio-cli` | |
