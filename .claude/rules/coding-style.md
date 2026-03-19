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

## Immutability

Prefer immutable data structures:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    name: str
    email: str

from typing import NamedTuple

class Point(NamedTuple):
    x: float
    y: float
```

## Formatting

- **black** for code formatting
- **isort** for import sorting
- **ruff** for linting

## Reference

See skill: `python-patterns` for comprehensive Python idioms and patterns.
