## 1. Add Lint/Type Tooling

- [x] 1.1 Run `uv add --dev ruff ty` and verify `pyproject.toml`'s `[dependency-groups] dev` and `uv.lock` are updated, and `uv run ruff --version` / `uv run ty --version` succeed
- [x] 1.2 Add a minimal `[tool.ruff]` section to `pyproject.toml` with `target-version = "py313"` (default rule set otherwise); verify `uv run ruff check .` and `uv run ruff format --check .` run without configuration errors

## 2. Make the Repo Pass Its Own Checks

- [x] 2.1 Fix the Ruff lint findings in `app.py` and `tests/` (currently 7, e.g. `datetime.timezone.utc` → `datetime.UTC` alias); verify `uv run ruff check .` exits 0
- [x] 2.2 Apply `uv run ruff format .` to `app.py` and `tests/` (currently 6 files need reformatting); verify `uv run ruff format --check .` exits 0 and `uv run pytest` still passes after formatting
- [x] 2.3 Fix the `ty` diagnostic in `tests/test_models.py` (`utcoffset()` returns `timedelta | None`); verify `uv run ty check` exits 0 with no diagnostics

## 3. GitHub Actions Workflow

- [ ] 3.1 Create `.github/workflows/ci.yml` with `on.push.branches: [master]` and `on.pull_request.branches: [master]`, a `concurrency` group keyed on the ref that cancels in-progress runs, and four jobs (`lint`, `format`, `typecheck`, `test`) each on `ubuntu-latest`
- [x] 3.2 In each job, check out the repo, install `uv` via `astral-sh/setup-uv@v7` pinned to Python 3.13, and run `uv sync --locked`; verify the workflow is valid YAML (`uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` or equivalent) and mirrors the commands from tasks 1-2 (`uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`, `uv run pytest`)
- [ ] 3.3 Push the workflow on a branch and open a PR against `master`; verify in the GitHub Actions UI that all four checks (`lint`, `format`, `typecheck`, `test`) run independently and each reports its own pass/fail status (not a single combined check)
- [ ] 3.4 Verify negative triggers by confirming (via the workflow's `on:` config and, if needed, a throwaway branch with no PR) that pushing to a non-`master` branch with no open PR against `master` does not start a run

## 4. Documentation and Manual Follow-up

- [ ] 4.1 Update `README.md` with a short "Continuous Integration" section describing the four checks and the local commands that reproduce them (`uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`, `uv run pytest`)
- [ ] 4.2 Document, as a manual post-merge step (not automatable in the workflow file), that a repo admin must enable "Require status checks to pass before merging" on `master` in GitHub's branch protection settings and select the four new checks; verify by recording the exact setting path in the README or a short note in this task, since the assistant applying this change cannot itself change GitHub repository settings
