## Context

See proposal.md - Why. The project is a single-package `uv`-managed FastAPI app (`app.py`, `tests/`) with no CI today and no `.github` directory. `pyproject.toml` pins `requires-python = ">=3.13"`, `.python-version` pins `3.13`, and `uv.lock` is committed — CI should reproduce the same environment a contributor gets from `uv sync`. The default branch is `master` (confirmed via `gh repo view`).

## Goals / Non-Goals

**Goals:**
- A single workflow file contributors can read top to bottom.
- Fast feedback: independent checks run in parallel, each visible as its own status check on a PR.
- Zero drift between local and CI tooling — the same `uv run <tool>` commands work identically on a contributor's machine and in CI.

**Non-Goals:**
- Any deployment, packaging, or release step (see specs/ci-pipeline - "No deployment behavior"; there is no hosting target yet).
- Enabling GitHub's "require status checks to pass" branch protection setting itself — that is a one-time manual repo-admin action in GitHub's UI/API, not something expressible in a workflow YAML file. It's called out as a task with a manual verification note.
- Caching strategy beyond what `astral-sh/setup-uv`'s built-in cache provides by default — no custom cache key tuning in this change.
- Dependabot / dependency-update automation — out of scope for this change.

## Decisions

### D1. One workflow file, four parallel jobs
`.github/workflows/ci.yml` defines a single workflow with four independent jobs — `lint`, `format`, `typecheck`, `test` — each running on `ubuntu-latest` with Python 3.13. Each job does its own checkout + `uv sync`, so a failure in one job doesn't hide or skip the others (satisfies "Independent, visible check outcomes"). A `concurrency` group cancels superseded runs on the same ref (new push to a PR cancels the previous run) to avoid wasting minutes.
- *Alternative*: one job with sequential steps. Rejected — a lint failure would abort before tests ran, and GitHub would show only one combined check instead of four, contradicting the spec's per-category visibility requirement.
- *Alternative*: a matrix over Python versions/OSes. Rejected per the user's choice (3.13 / Ubuntu only) — this app targets one runtime, so a matrix would only slow CI down for no coverage benefit.

### D2. `astral-sh/setup-uv` for the `uv` toolchain, `uv sync` for deps
Use the official `astral-sh/setup-uv@v7` action (pinned to a major version tag) to install `uv`, then `uv sync --locked` (fails if `uv.lock` is out of date, rather than silently re-resolving) so CI installs exactly what `uv.lock` pins — matching "Dependency installation matches local development" and catching an unsynced lockfile as a CI failure rather than a silent drift.
- *Alternative*: `pip install uv` then `uv sync`. Rejected — the setup-uv action also pins/caches the `uv` binary version and wires up its dependency cache, saving a step and giving reproducible `uv` versions across runs.

### D3. Ruff for lint and format, `ty` for types — invoked the same way locally and in CI
Add `ruff` and `ty` to `[dependency-groups] dev` (`uv add --dev ruff ty`) so `uv run ruff ...` / `uv run ty ...` work identically in a contributor's shell and in CI — no separate "CI-only" tool install. Jobs run:
- lint: `uv run ruff check .`
- format: `uv run ruff format --check .`
- typecheck: `uv run ty check`
A minimal `[tool.ruff]` block in `pyproject.toml` sets `target-version = "py313"` (matching `requires-python`); default rule set otherwise, so this change doesn't also become a large reformatting/lint-fixing pass. Any violations Ruff/`ty` find on the existing `app.py`/`tests/` are fixed as part of this change so the pipeline starts green (tracked as its own task, not folded into the workflow-file task).
- *Alternative*: Black + Flake8 + mypy. Rejected — Ruff replaces both Black and Flake8 in one fast tool and the project's own FastAPI/uv convention (per the fastapi skill's tooling guidance) already points at Ruff + `ty`; using them keeps local and CI tooling identical to what's recommended for this stack.

### D4. Test job runs `uv run pytest` with the existing suite, no new test infra
The `test` job runs `uv run pytest`; `pyproject.toml` already sets `testpaths = ["tests"]`, so no new pytest configuration is needed. No coverage threshold or reporting is added in this change — that would be a separate, explicit decision with its own trade-offs (coverage gating can block valid PRs on incidental line misses).

### D5. Workflow triggers: `push` to `master` and `pull_request` targeting `master`
```yaml
on:
  push:
    branches: [master]
  pull_request:
    branches: [master]
```
This satisfies all three trigger scenarios in the spec: a direct push to `master` runs it, a PR targeting `master` runs it (on the PR's head commit, via GitHub's standard `pull_request` event semantics), and a push to any other branch with no PR open against `master` does not trigger it.

## Risks / Trade-offs

- [`uv sync --locked` fails the build if `uv.lock` is stale] → Intentional: surfaces a forgotten `uv lock` as a fast, clear CI failure rather than CI silently using different versions than local dev.
- [Adding Ruff/`ty` now may surface pre-existing lint/type issues in `app.py` or `tests/`] → Addressed by a dedicated task to run both tools locally and fix findings before the workflow is expected to pass, so the pipeline isn't red on day one.
- [Branch protection isn't actually enforced by this change] → Documented as a manual step in tasks.md with a verification note; the workflow alone only reports status, it can't require it.
- [Four separate jobs use more Action minutes than one combined job] → Acceptable for a small codebase; parallel jobs mean wall-clock time stays low despite the extra minute count, and public repos get free Actions minutes.

## Migration Plan

Additive only — no existing behavior changes and nothing to migrate. Rollout is: merge the workflow file (it starts protecting future PRs immediately), then a repo admin manually turns on "Require status checks to pass" for `master` naming the four new checks. Rollback is deleting or disabling `.github/workflows/ci.yml`; no data or runtime state is involved.
