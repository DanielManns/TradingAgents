# Git Workflow

## Commit Message Format
```
<type>: <description>

<optional body>
```

Types: feat, fix, refactor, docs, test, chore, perf, ci

Note: Attribution disabled globally via ~/.claude/settings.json.

## Pull Request Workflow

When creating PRs:
1. Analyze full commit history (not just latest commit)
2. Use `git diff [base-branch]...HEAD` to see all changes
3. Draft comprehensive PR summary
4. Include test plan with TODOs
5. Push with `-u` flag if new branch

## Incorporating PR Comments

Before incorporating PR review comments into the feature branch:

1. **Pull the default branch** (usually `dev`) to avoid merge conflicts:
   ```bash
   git fetch origin
   git merge origin/dev
   ```
2. Resolve conflicts if any exist
3. Then apply the PR comments
4. Commit and push changes

> For the full development process (planning, TDD, code review) before git operations,
> see [development-workflow.md](./development-workflow.md).
