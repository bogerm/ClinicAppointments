## Why

The repository has automated tests but no automated way to run them. Every push and pull request currently relies on someone remembering to run `uv run pytest` locally; nothing stops broken code, unformatted code, or a type error from landing on `master`. A GitHub Actions pipeline gives every push and PR an automatic, consistent check.

## What Changes

- Add a GitHub Actions workflow (`.github/workflows/ci.yml`) that runs on every push to `master` and every pull request targeting `master`.
- The workflow installs the project with `uv` (matching local development) on Python 3.13 / Ubuntu, then runs, as separate jobs: Ruff lint, Ruff format check, `ty` static type check, and the `pytest` suite.
- A required branch protection expectation on `master`: the workflow's checks must pass before a PR can merge (documented in the proposal/design; enabling the GitHub setting itself is a manual repo-admin action called out in tasks, since it is not something a workflow file can do).
- Add `ruff` and `ty` as dev dependencies (`uv add --dev ruff ty`) and minimal configuration for them in `pyproject.toml`.
- No deployment/CD step is introduced in this change — there is no hosting target for this API yet. A future change can add a CD capability once one exists.

## Capabilities

### New Capabilities
- `ci-pipeline`: Automated checks (lint, format, type-check, tests) that run on GitHub Actions for every push and pull request against `master`, gating code changes on those checks passing.

### Modified Capabilities
<!-- None: this change adds tooling/CI, not application behavior. The existing appointment-slots and appointment-bookings capabilities are unaffected — no request/response behavior changes. -->

## Impact

- **New files**: `.github/workflows/ci.yml`.
- **Modified files**: `pyproject.toml` (new `dev` dependencies `ruff`, `ty`; new `[tool.ruff]` config); `uv.lock` (updated by `uv add`).
- **No application code (`app.py`) or API behavior changes.**
- **Process impact**: pull requests will show CI status checks; `master` is expected to be protected once this lands (manual GitHub setting, called out as a task).
- **Assumptions recorded for the specs** (not stated by the user): the default branch is `master` (confirmed via `gh repo view`); "CI/CD" here means CI only, no deployment target exists yet; lint/format/type-check use Ruff and `ty` per the project's established FastAPI/uv tooling convention; Python 3.13 on `ubuntu-latest` only, matching `pyproject.toml`'s `requires-python = ">=3.13"` and the checked-in `.python-version`.
