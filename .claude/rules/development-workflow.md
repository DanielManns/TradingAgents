# Development Workflow

> This file extends [common/git-workflow.md](./git-workflow.md) with the full feature development process that happens before git operations.

The Feature Implementation Workflow describes the development pipeline: research, planning, TDD, code review, and then committing to git.

## Principle — Minimal Code

Write only the least amount of custom code necessary. If a well-maintained Python library already implements a piece of functionality, use it instead of building from scratch. Glue code and thin wrappers are preferred over reimplementation. Every ticket should start by asking: **"Is there a library that already does this?"**

## Principle — Fail Loud, Never Silently

Silent errors are fatal to this project. If something unexpected happens, the application must **crash with a descriptive error message** rather than swallow the error and continue. Never return `None` as a stand-in for an error condition — raise an exception instead. A traceback we can see is always better than a wrong result we can't.

- **Raise, don't return `None`:** If a function cannot produce a valid result, raise a descriptive exception (e.g., `ValueError`, `KeyError`, or a custom exception). Callers should not have to guess whether `None` means "no data" or "something went wrong".
- **No bare `except` / `except Exception: pass`:** Never catch an exception just to silence it. If you catch, either handle it meaningfully or re-raise.
- **Assertions for invariants:** Use `assert` or explicit checks for conditions that should always hold. If they don't, something is wrong and we want to know immediately.

## Principle — Zen of Python (PEP 20)

The most essential rules from `import this`:

### Explicit is better than implicit
```python
# Bad — what does process do? what is x?
def process(x):
    return x * 2 + 1

# Good — intent is clear from name, types, and structure
def double_and_increment(value: int) -> int:
    return value * 2 + 1
```

### Simple is better than complex
```python
# Bad — stacked filters obscure intent
result = [x for x in range(100) if x % 2 == 0 if x % 3 == 0 if x > 10]

# Good — single clear condition
divisible_by_six = [x for x in range(100) if x % 6 == 0 and x > 10]
```

### Flat is better than nested
```python
# Bad — deep nesting
if user:
    if user.is_active:
        if user.has_permission:
            do_thing()

# Good — guard clauses
if not user:
    return
if not user.is_active:
    return
if not user.has_permission:
    return
do_thing()
```

### Readability counts
```python
# Bad — cryptic names
x = lambda t: A * sin(2 * pi * f * t + p)

# Good — meaningful names
angular_freq = 2 * pi * frequency
wave = lambda t: amplitude * sin(angular_freq * t + phase)
```

### Errors should never pass silently
```python
# Bad — swallowed error
try:
    risky_operation()
except:
    pass

# Good — handle or re-raise
try:
    risky_operation()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise
```

### In the face of ambiguity, refuse the temptation to guess
```python
# Bad — caller must guess what a, b, c mean
def calculate(a, b, c):
    return a + b * c

# Good — unambiguous parameters
def calculate_cost(base: float, rate: float, quantity: int) -> float:
    return base + (rate * quantity)
```

### If the implementation is hard to explain, it's a bad idea
```python
# Bad — explain this in one sentence
result = sum([x * y for x in range(10) for y in range(10) if (x + y) % 3 == 0])

# Good — each step is obvious
products = [x * y for x in range(10) for y in range(10) if (x + y) % 3 == 0]
result = sum(products)
```

### Simple functions are better than complex classes
```python
# Bad — a class that only wraps a single method
class PriceCalculator:
    def __init__(self, base: float, tax_rate: float):
        self.base = base
        self.tax_rate = tax_rate

    def calculate(self) -> float:
        return self.base * (1 + self.tax_rate)

total = PriceCalculator(100, 0.2).calculate()

# Good — a plain function does the job
def calculate_price(base: float, tax_rate: float) -> float:
    return base * (1 + tax_rate)

total = calculate_price(100, 0.2)
```

Only reach for a class when you need **shared mutable state** or **multiple methods that operate on the same data**. If a function can do it, use a function.

### Less code is better than more code
```python
# Bad — verbose and redundant
def is_eligible(user: User) -> bool:
    if user.age >= 18:
        if user.is_active:
            return True
        else:
            return False
    else:
        return False

# Good — same logic, minimal expression
def is_eligible(user: User) -> bool:
    return user.age >= 18 and user.is_active
```

Fewer lines mean fewer bugs, less to read, and less to maintain. If the same functionality can be expressed in fewer lines without sacrificing readability, always prefer the shorter version.

## Feature Implementation Workflow

0. **Research & Reuse** _(mandatory before any new implementation)_
   - **GitHub code search first:** Run `gh search repos` and `gh search code` to find existing implementations, templates, and patterns before writing anything new.
   - **Library docs second:** Use Context7 or primary vendor docs to confirm API behavior, package usage, and version-specific details before implementing.
   - **Exa only when the first two are insufficient:** Use Exa for broader web research or discovery after GitHub search and primary docs.
   - **Check package registries:** Search npm, PyPI, crates.io, and other registries before writing utility code. Prefer battle-tested libraries over hand-rolled solutions.
   - **Search for adaptable implementations:** Look for open-source projects that solve 80%+ of the problem and can be forked, ported, or wrapped.
   - Prefer adopting or porting a proven approach over writing net-new code when it meets the requirement.

1. **Plan First**
   - Use **planner** agent to create implementation plan
   - Generate planning docs before coding: PRD, architecture, system_design, tech_doc, task_list
   - Identify dependencies and risks
   - Break down into phases

2. **TDD Approach**
   - Use **tdd-guide** agent
   - Write tests first (RED)
   - Implement to pass tests (GREEN)
   - Refactor (IMPROVE)
   - Verify 80%+ coverage

3. **Code Review**
   - Use **code-reviewer** agent immediately after writing code
   - Address CRITICAL and HIGH issues
   - Fix MEDIUM issues when possible

4. **Commit & Push**
   - Detailed commit messages
   - Follow conventional commits format
   - See [git-workflow.md](./git-workflow.md) for commit message format and PR process
