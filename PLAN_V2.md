# Alternative Implementation Plan: Stock Picker CLI (Outside-In)

## Context

**End-User-Story:** "Ich will ein CLI-Tool, das mir die 10 Aktien auswahlt, die im nachsten Monat die hochste Rendite bringen. Nach 30 Tagen rufe ich das Tool erneut auf und es sagt mir: verkaufe X, kaufe Y, oder halte alles."

**Ansatz:** Statt 15 Infrastruktur-Tickets bottom-up (alter Plan), arbeiten wir **Outside-In** vom End-User-Value ruckwarts. Bei jedem Ticket fragen wir: *"Welche Funktionalitat brauche ich als nachstes, um dem Ziel einen Schritt naher zu kommen?"* Tickets werden nur geschrieben wenn sie zwingend notig sind.

**Was existiert bereits:**
- `propagate(ticker, date)` → `(final_state, "BUY"/"SELL"/"HOLD")` (Multi-Agent-Analyse)
- Typer CLI mit `@app.command()` Pattern (`cli/main.py`)
- `SignalProcessor` extrahiert BUY/SELL/HOLD aus Text
- Konfigurierbare Time Horizon (`analysis_period`, Ticket 2 erledigt)
- YFinance-Datenintegration, LLM-Clients, pytest + CI

**Designprinzipien:**
1. Jedes Ticket liefert sichtbaren End-User-Value
2. Kein Gold-Plating: kein Position Sizing, keine Transaktionskosten, kein Backtesting — der User will nur wissen: welche 10 Aktien kaufen, und wann tauschen
3. Maximale Wiederverwendung der existierenden `propagate()` Pipeline
4. Minimale neue Abhangigkeiten

---

## Recherche-Ergebnisse

**Existierende Ansatze (Web-Recherche):**
- **OpenBB Terminal** hat Stock-Screening, aber ist ein ganzes Platform-Produkt — Overkill
- **LangChain/CrewAI Finance Templates** orchestrieren LLM-Agents fur Aktienanalyse — genau was TradingAgents bereits macht
- **Typischer Flow in Open-Source-Tools:** Universe → Screen → Rank → Select → Persist → Rebalance
- **Momentum-basierte Selektion** ist der einfachste und am haufigsten genutzte Ansatz fur monatliches Rebalancing

**Kerninsight:** TradingAgents hat den schwierigen Teil (Multi-Agent-Analyse mit Debate) bereits gebaut. Was fehlt ist nur die **Orchestrierungsschicht**: viele Aktien analysieren, ranken, merken, vergleichen.

---

## Tickets (5 Stück, strikt priorisiert)

### Ticket 1: `pick` — Top-10-Aktien auswahlen und anzeigen
**Branch:** `feature/stock-picker`
**Frage:** *"Was brauche ich, um dem User 10 Aktien zu empfehlen?"*
**Antwort:** Eine Liste von Kandidaten, Batch-Analyse, Ranking, CLI-Output.

- **Ticker-Universe:** Kuratierte Liste von ~30 S&P 500 Large-Cap Aktien als Python-Liste in `tradingagents/portfolio/universe.py` (kein YFinance-Screening, keine Datenbank — einfach eine Liste)
- **Batch-Analyse:** `BatchRunner` in `tradingagents/portfolio/batch_runner.py` — loopt uber `propagate()`, uberspringt Fehler graceful, zeigt Progress via Rich
- **Scoring:** Einfaches Keyword-Scoring aus `process_signal()` Ergebnis: BUY=1.0, HOLD=0.0, SELL=-1.0. Zusatzlich: `final_trade_decision` Text wird fur spatere Anzeige gespeichert
- **Selection:** Top 10 nach Score sortiert. Bei Gleichstand: alphabetisch
- **Persistenz:** Ergebnis als JSON in `portfolio_data/latest_picks.json` speichern (Datum, Ticker, Score, Decision, Kurzbegrundung)
- **CLI:** `tradingagents pick` Befehl — Rich-Tabelle mit Rang, Ticker, Signal, Kurzbegrundung

**Dateien:**
- Neu: `tradingagents/portfolio/__init__.py`
- Neu: `tradingagents/portfolio/universe.py` (~30 Zeilen)
- Neu: `tradingagents/portfolio/batch_runner.py` (~80 Zeilen)
- Neu: `tradingagents/portfolio/scorer.py` (~40 Zeilen)
- Neu: `tradingagents/portfolio/persistence.py` (~50 Zeilen)
- Modify: `cli/main.py` — neuer `pick` Command
- Neu: `tests/test_pick.py`

**AC:** `tradingagents pick` analysiert ~30 Aktien, zeigt Top 10 als Tabelle, speichert Ergebnis als JSON. Fehler bei einzelnen Aktien blockieren nicht den Rest.

---

### Ticket 2: `rebalance` — Nach 30 Tagen: Verkaufen, Kaufen oder Halten
**Branch:** `feature/rebalance`
**Frage:** *"Was brauche ich, um dem User zu sagen ob er tauschen soll?"*
**Antwort:** Vorherige Picks laden, neu analysieren, Scores vergleichen, Aktionen empfehlen.

- **State laden:** `latest_picks.json` einlesen
- **Re-Analyse:** Alle aktuellen Holdings + alle Universe-Kandidaten analysieren (BatchRunner aus T1)
- **Vergleich mit Hurdle:** Ein Holding wird nur dann durch einen neuen Kandidaten ersetzt, wenn der Score-Unterschied > `min_improvement` (default 0.3). Das verhindert unnotiges Hin-und-Her-Traden
- **Aktionsplan generieren:**
  - HOLD: Aktie bleibt (Score immer noch gut genug)
  - SELL + BUY: Aktie wird ersetzt (neuer Kandidat deutlich besser)
  - Ergebnis: Immer genau 10 Aktien am Ende
- **Persistenz:** Neuen State als `latest_picks.json` speichern (uberschreibt alten), alten State als `portfolio_data/history/YYYY-MM-DD.json` archivieren
- **CLI:** `tradingagents rebalance` — Rich-Tabelle mit Aktionen (HOLD/SELL/BUY), vorherigem Score, neuem Score

**Dateien:**
- Neu: `tradingagents/portfolio/rebalancer.py` (~100 Zeilen)
- Modify: `tradingagents/portfolio/persistence.py` — History-Archivierung
- Modify: `cli/main.py` — neuer `rebalance` Command
- Neu: `tests/test_rebalance.py`

**AC:** `tradingagents rebalance` ladt vorherige Picks, analysiert alle Kandidaten neu, gibt klare HOLD/SELL+BUY Empfehlungen. Hurdle-Logik verhindert unnotiges Trading. Immer 10 Aktien am Ende. Alter State wird archiviert.

**Hinweis:** Wenn kein vorheriger State existiert, Fehlermeldung: "Kein Portfolio gefunden. Bitte zuerst `tradingagents pick` ausfuhren."

---

### Ticket 3: `status` — Aktuellen Portfolio-Stand anzeigen
**Branch:** `feature/portfolio-status`
**Frage:** *"Was brauche ich, damit der User jederzeit seinen aktuellen Stand sehen kann?"*
**Antwort:** Gehaltene Aktien + aktuelle Kurse + einfache Performance.

- **Status-Anzeige:** Ladt `latest_picks.json`, holt aktuelle Kurse via YFinance, zeigt:
  - Ticker, Signal (BUY/HOLD), Datum des Picks
  - Kurs bei Pick vs. aktueller Kurs
  - Prozentuale Anderung seit Pick
  - Gleichgewichtetes Portfolio-Gesamtperformance
- **Benchmark:** SPY-Performance im gleichen Zeitraum zum Vergleich
- **CLI:** `tradingagents status` — Rich-Tabelle + Summary

**Dateien:**
- Neu: `tradingagents/portfolio/status.py` (~80 Zeilen)
- Modify: `cli/main.py` — neuer `status` Command
- Neu: `tests/test_status.py`

**AC:** `tradingagents status` zeigt Portfolio-Ubersicht mit Performance vs. SPY. Funktioniert ohne LLM-Calls (nur YFinance-Preise).

---

### Ticket 4: Analyse-Caching — Batch-Lauf bezahlbar machen
**Branch:** `feature/analysis-caching`
**Frage:** *"Der Batch-Lauf uber 30 Aktien ist teuer (~300 LLM-Calls). Was brauche ich, damit ich nicht jedes Mal alles neu analysieren muss?"*
**Antwort:** Caching + Rate Limiting.

- **Analysis-Cache:** `AnalysisCache` in `tradingagents/portfolio/cache.py` — cached `propagate()` Ergebnisse auf Disk (Key: ticker+date, TTL: 7 Tage konfigurierbar). Rebalance uberspringt Cache-Hits
- **Rate Limiting:** Konfigurierbarer Delay zwischen `propagate()` Calls (default 1s)
- **Budget-Cap:** Optional `max_budget_usd` — stoppt Batch wenn geschatztes Budget uberschritten
- **Progress:** Rich Progress Bar mit ETA und Kosten-Schatzung
- **Config:** Neue Felder in `default_config.py`: `cache_ttl_days`, `batch_delay_seconds`, `max_batch_budget_usd`

**Dateien:**
- Neu: `tradingagents/portfolio/cache.py` (~80 Zeilen)
- Modify: `tradingagents/portfolio/batch_runner.py` — Cache-Integration, Rate Limiting, Budget Cap
- Modify: `tradingagents/default_config.py`
- Neu: `tests/test_cache.py`

**AC:** Zweiter Batch-Lauf am selben Tag nutzt Cache (0 LLM-Calls). Rate Limiting halt Delays ein. Budget-Cap stoppt bei Uberschreitung.

---

### Ticket 5: Besseres Scoring mit LLM — Feinere Unterscheidung
**Branch:** `feature/conviction-scoring`
**Frage:** *"BUY=1.0/HOLD=0.0/SELL=-1.0 ist zu grob. Was brauche ich fur bessere Ranking-Qualitat?"*
**Antwort:** LLM-basierte Conviction-Extraktion mit Pydantic.

- **Structured Scoring:** `ConvictionScorer` in `tradingagents/portfolio/conviction.py` — nutzt `instructor` + Pydantic um einen Float-Score (-1.0 bis +1.0) aus `final_trade_decision` zu extrahieren. "Strong BUY" → 0.9, "Cautious BUY" → 0.4, etc.
- **Fallback:** Bei LLM-Fehler → Keyword-Scoring aus T1
- **Dependency:** `instructor>=1.7,<2.0` zu `pyproject.toml` hinzufugen
- **Scorer austauschbar:** `BatchRunner` akzeptiert einen `scorer` Parameter (default: KeywordScorer aus T1, optional: ConvictionScorer)

**Dateien:**
- Neu: `tradingagents/portfolio/conviction.py` (~60 Zeilen)
- Modify: `tradingagents/portfolio/scorer.py` — Scorer-Interface
- Modify: `tradingagents/portfolio/batch_runner.py` — austauschbarer Scorer
- Modify: `pyproject.toml` — instructor dependency
- Neu: `tests/test_conviction.py`

**AC:** ConvictionScorer unterscheidet zwischen "Strong BUY" (0.9) und "Cautious BUY" (0.4). Ranking-Qualitat verbessert gegenuber Keyword-Scoring. Fallback funktioniert.

---

## Ticket-Abhangigkeiten

```
T1 (pick) ──→ T2 (rebalance) ──→ T3 (status)
                                      │
T1 (pick) ──→ T4 (caching) ←─────────┘

T1 (pick) ──→ T5 (besseres scoring)

T6 (lint-cleanup) ── unabhangig, jederzeit machbar
```

- **T1 + T2** liefern die komplette User-Story (Kern-MVP)
- **T3** ist Quality-of-Life (kein LLM notig, nur Preise)
- **T4** ist Kostenoptimierung (wichtig fur regelmasige Nutzung)
- **T5** ist Qualitatsverbesserung (bessere Rankings)

**T4 und T5 sind unabhangig voneinander und konnen parallel entwickelt werden.**

---

## Vergleich mit altem Plan

| | Alter Plan | Neuer Plan |
|---|---|---|
| Tickets | 15 | 5 |
| Erster End-User-Value | Ticket 9 (Portfolio Construction) | Ticket 1 (pick) |
| Neue Dependencies | 6 (PyPortfolioOpt, bt, pandera, sqlite-utils, instructor, quantstats-lumi) | 1 (instructor, nur T5) |
| Neue Packages | 3 (portfolio/, backtest/, evaluation/) | 1 (portfolio/) |
| Position Sizing | Ja (Equal Weight + PyPortfolioOpt) | Nein (einfach "diese 10 Aktien") |
| Backtesting | Ja (Dual-Engine) | Nein |
| Transaktionskosten | Ja | Nein |
| Sektor-Diversifikation | Ja | Nein |
| Persistenz | SQLite + JSON | Nur JSON |

**Trade-off:** Der neue Plan liefert schneller Wert, ist aber weniger feature-complete. Features wie Backtesting, Position Sizing und Sektor-Diversifikation konnen spater als Folge-Tickets hinzugefugt werden, wenn der User sie braucht.

---

## Progress Log

| Ticket | Status | Branch | Depends on | Notes |
|--------|--------|--------|------------|-------|
| 1 | Not started | `feature/stock-picker` | — | Kern-MVP Teil 1 |
| 2 | Not started | `feature/rebalance` | T1 | Kern-MVP Teil 2 |
| 3 | Not started | `feature/portfolio-status` | T1 | Quality-of-Life |
| 4 | Not started | `feature/analysis-caching` | T1 | Kostenoptimierung |
| 5 | Not started | `feature/conviction-scoring` | T1 | Qualitatsverbesserung |
| 6 | Not started | `feature/lint-cleanup` | — | Ruff per-file-ignores auflosen |

---

### Ticket 6: Lint-Cleanup — Ruff-Ignores in bestehendem Code auflosen
**Branch:** `feature/lint-cleanup`
**Frage:** *"Wir haben pre-commit mit ruff eingefuhrt, aber mussten viele bestehende Violations per-file ignorieren. Was brauche ich, damit der gesamte Code sauber ist?"*
**Antwort:** Die per-file-ignores in `pyproject.toml` Schritt fur Schritt auflosen.

- **`cli/main.py`** — `E402` (imports nach `load_dotenv()`), `F403`/`F405` (star import aus `cli.utils`): Star-Import durch explizite Imports ersetzen. `load_dotenv()` in ein fruhes Bootstrap-Modul verschieben oder `E402`-Ignore belassen (bewusste Design-Entscheidung)
- **`cli/utils.py`** — `F821` (undefined `console`): Fehlende `console = Console()` Instanz hinzufugen oder als Parameter durchreichen
- **`tests/*`** — `E501` (lange Zeilen), `B017` (blind `pytest.raises(Exception)`): Lange Zeilen umbrechen, spezifische Exception-Typen in `pytest.raises` verwenden
- **`tradingagents/agents/*`** — `E501` (lange Prompt-Strings), `F403`/`F405` (star imports), `B007` (unused loop vars): Prompts in Multiline-Strings oder Konstanten extrahieren, star imports durch explizite Imports ersetzen, unused loop vars mit `_` prefixen
- **`tradingagents/agents/utils/agent_states.py`** — `F403` (star import): Explizite Imports verwenden
- **`tradingagents/graph/*`** — `E501` (lange Strings), `F403`/`F405` (star imports): Star imports auflosen, lange Strings umbrechen
- **`tradingagents/dataflows/*`** — `E501` (lange Zeilen), `B904` (missing `raise ... from`): Zeilen umbrechen, Exception-Chaining mit `from err` hinzufugen
- **`tests/test_analysis_horizon.py`** — `ImportError` (broken import `get_balance_sheet` aus `agent_utils`): Import fixen oder Test an aktuelle API anpassen. Aktuell per `--ignore` aus pre-commit pytest-Hook ausgeschlossen

**Dateien:**
- Modify: `cli/main.py`, `cli/utils.py`
- Modify: `tests/test_rebalance.py`, `tests/test_analysis_horizon.py`
- Modify: `tradingagents/agents/**/*.py` (Analysts, Managers, Researchers, Trader)
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents/graph/setup.py`, `tradingagents/graph/signal_processing.py`
- Modify: `tradingagents/dataflows/alpha_vantage_common.py`, `tradingagents/dataflows/alpha_vantage_indicator.py`
- Modify: `pyproject.toml` — per-file-ignores entfernen
- Modify: `.pre-commit-config.yaml` — `--ignore=tests/test_analysis_horizon.py` aus pytest-Hook entfernen

**AC:** Alle `[tool.ruff.lint.per-file-ignores]` Eintrage aus `pyproject.toml` entfernt. `--ignore` aus `.pre-commit-config.yaml` pytest-Hook entfernt. `ruff check .` und `pre-commit run --all-files` bestehen ohne Ignores. Kein Verhaltensanderung im Code.

---

## Verification

Nach jedem Ticket:
1. `uv run pytest tests/` — alle Tests grun
2. Manueller Test mit `--dry-run` oder Mock-propagate (ohne echte LLM-Calls)
3. Code-Review via code-reviewer Agent

End-to-End nach T2:
```bash
# Erster Lauf: 10 Aktien auswahlen
tradingagents pick

# 30 Tage spater: Rebalance
tradingagents rebalance
```
