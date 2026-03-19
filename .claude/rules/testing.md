---
paths:
  - "**/*.py"
  - "**/*.pyi"
---
# Python Testing

> This file extends [common/testing.md](../common/testing.md) with Python specific content.

## Framework

Use **pytest** as the testing framework.

## Coverage

```bash
pytest --cov=src --cov-report=term-missing
```

## Test Organization

Use `pytest.mark` for test categorization:

```python
import pytest

@pytest.mark.unit
def test_calculate_total():
    ...

@pytest.mark.integration
def test_database_connection():
    ...
```

## What NOT to test

- **Static data / configuration lists** — Python guarantees lists, dicts, and literals work. Don't write tests that just assert `isinstance(MY_LIST, list)` or check the length of a hardcoded constant. Test *behaviour*, not *data*.
- **Framework internals** — don't test that dataclasses store fields correctly, that enums have values, etc.

```python
# Bad — no behaviour being tested
def test_universe_is_list():
    assert isinstance(UNIVERSE, list)  # useless

# Good — tests real behaviour
def test_batch_runner_uses_all_tickers_from_universe():
    called = []
    def fn(t, d): called.append(t); return {}, "BUY"
    BatchRunner(fn).run(UNIVERSE, "2024-01-01")
    assert set(called) == set(UNIVERSE)
```

## Parametrize repeated cases

Use `@pytest.mark.parametrize` whenever multiple test cases share the same logic with different inputs/outputs. Never write separate test functions for each input variant.

```python
# Bad
def test_buy_scores_one(): assert scorer.score("BUY") == 1.0
def test_sell_scores_minus_one(): assert scorer.score("SELL") == -1.0

# Good
@pytest.mark.parametrize("signal,expected", [
    ("BUY", 1.0),
    ("SELL", -1.0),
    ("HOLD", 0.0),
])
def test_keyword_scorer(signal, expected):
    assert KeywordScorer().score(signal) == expected
```

## Test strength

- Tests must verify **new functionality**, not just that code runs without crashing
- For each function, test: happy path, edge cases (empty input, boundary values), and error/failure handling
- Use specific assertions — `assert result == expected`, not just `assert result`

## Reference

See skill: `python-testing` for detailed pytest patterns and fixtures.
