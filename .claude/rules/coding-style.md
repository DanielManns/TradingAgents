---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Coding Style

> This file extends [common/coding-style.md](../common/coding-style.md) with Python specific content.

## Standards

- Follow **PEP 8** conventions
- Use **type annotations** on all function signatures

## Imports

- **All imports at module level** — never inside functions, except when unavoidable (e.g. circular imports or optional heavy dependencies)
- Group imports: stdlib → third-party → internal, separated by blank lines

## Constants

- Module-level constants in **UPPER_CASE**
- Never define constants (dicts, strings, numbers) inline inside functions if they are static — define them at module level

```python
# Good
SIGNAL_STYLES: dict[str, str] = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}

def render(signal: str) -> str:
    return SIGNAL_STYLES.get(signal, "white")

# Bad
def render(signal: str) -> str:
    signal_styles = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}  # repeated allocation
    return signal_styles.get(signal, "white")
```

## Function Cleanliness

- CLI command functions (`@app.command()`) must stay thin: validate input, call helpers, print output
- Extract complex logic (table building, mock creation, graph setup) into named helper functions
- A function that does more than ~20 lines of substantive logic likely needs a helper extracted

```python
# Good
def _build_result_table(picks, top_n, date) -> Table: ...
def _make_mock_propagate_fn(): ...

@app.command()
def pick(...):
    ...
    console.print(_build_result_table(top_picks, top_n, analysis_date))

# Bad
@app.command()
def pick(...):
    table = Table(...)
    table.add_column(...)
    for row in ...:
        table.add_row(...)
    console.print(table)
```

## Data Structures — Pydantic Over Dataclasses

Always use **Pydantic `BaseModel`** instead of `dataclasses` or `TypedDict` for data structures. Pydantic provides validation, `model_dump()` for JSON serialization, `model_validate()` for deserialization, and `model_copy(update={...})` for immutable updates — all without custom code. Use `ConfigDict(frozen=True)` for immutable models. Centralize models in a dedicated `models.py` module per package.

```python
from pydantic import BaseModel, ConfigDict

class Pick(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    signal: str = ""
    score: float = 0.0
```

## Formatting

- **black** for code formatting
- **isort** for import sorting
- **ruff** for linting

## Reference

See skill: `python-patterns` for comprehensive Python idioms and patterns.
