## Purpose

Automatically checks every push and pull request against `master` for lint, formatting, type, and test correctness using GitHub Actions, so problems are caught before merge instead of relying on manual local runs.

## ADDED Requirements

### Requirement: Workflow triggers
A GitHub Actions workflow SHALL run on every push to `master` and on every pull request whose target branch is `master`.

#### Scenario: Push to master triggers the workflow
- **WHEN** a commit is pushed directly to `master`
- **THEN** the workflow runs

#### Scenario: Pull request triggers the workflow
- **WHEN** a pull request is opened or updated targeting `master`
- **THEN** the workflow runs against the pull request's head commit

#### Scenario: Push to an unrelated branch does not trigger the workflow
- **WHEN** a commit is pushed to a branch other than `master`, with no open pull request targeting `master` from it
- **THEN** the workflow does not run

### Requirement: Dependency installation matches local development
The workflow SHALL install project dependencies using `uv`, on Python 3.13, the same tool and version used for local development (per `pyproject.toml`'s `requires-python` and the checked-in `.python-version`).

#### Scenario: Dependencies resolve from the committed lockfile
- **WHEN** the workflow installs dependencies
- **THEN** it uses `uv` and the versions installed match those pinned in the repository's `uv.lock`

### Requirement: Lint check
The workflow SHALL run a lint check over the Python source and fail the workflow if it reports any violation.

#### Scenario: Lint violation fails the workflow
- **WHEN** the code being checked contains a lint violation (e.g. an unused import)
- **THEN** the lint job/step exits non-zero and the overall workflow run is marked failed

#### Scenario: Clean code passes the lint check
- **WHEN** the code being checked has no lint violations
- **THEN** the lint job/step succeeds

### Requirement: Format check
The workflow SHALL verify that the Python source is already formatted according to the project's formatting tool, without modifying files, and fail if any file would be reformatted.

#### Scenario: Unformatted file fails the workflow
- **WHEN** a Python file does not match the project's formatting rules
- **THEN** the format-check job/step exits non-zero and the overall workflow run is marked failed

#### Scenario: Correctly formatted code passes the check
- **WHEN** every Python file already matches the project's formatting rules
- **THEN** the format-check job/step succeeds

### Requirement: Static type check
The workflow SHALL run a static type check over the Python source and fail the workflow if it reports any type error.

#### Scenario: Type error fails the workflow
- **WHEN** the code being checked contains a static type error
- **THEN** the type-check job/step exits non-zero and the overall workflow run is marked failed

#### Scenario: Type-correct code passes the check
- **WHEN** the code being checked has no static type errors
- **THEN** the type-check job/step succeeds

### Requirement: Automated test suite execution
The workflow SHALL run the project's automated test suite and fail the workflow if any test fails.

#### Scenario: Failing test fails the workflow
- **WHEN** any test in the suite fails or errors
- **THEN** the test job/step exits non-zero and the overall workflow run is marked failed

#### Scenario: Passing suite succeeds
- **WHEN** every test in the suite passes
- **THEN** the test job/step succeeds

### Requirement: Independent, visible check outcomes
Lint, format, type-check, and test SHALL run as independently reported checks (e.g. separate jobs) so a contributor can see which category failed without needing to fail fast on the first failing one.

#### Scenario: One check fails while others still run and report
- **WHEN** the lint check fails but the code has no type errors and all tests pass
- **THEN** the pull request shows the lint check as failed and the type-check and test checks as passed (not skipped or hidden)

### Requirement: No deployment behavior
This capability SHALL NOT deploy, publish, or release any artifact. Its scope ends at reporting pass/fail status on the four checks above.

#### Scenario: A fully passing run performs no deployment
- **WHEN** every check (lint, format, type-check, tests) passes on a push to `master`
- **THEN** no deployment, package publish, or release step runs as part of this workflow
