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
