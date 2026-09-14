# Clinic Appointment Booking API

Clinicians publish time slots, patients book them. Built with FastAPI, managed with [uv](https://docs.astral.sh/uv/).
Storage is in-memory: data is lost on restart and is not shared between workers, so run a single worker.

## Setup

```bash
uv sync
```

## Run

```bash
uv run fastapi dev      # development server with reload, http://127.0.0.1:8000
uv run fastapi run      # production-style server
```

Interactive docs: http://127.0.0.1:8000/docs

## Test

```bash
uv run pytest
```

## Continuous Integration

Every push to `master` and every pull request targeting `master` runs [`.github/workflows/ci.yml`](.github/workflows/ci.yml), which checks lint, formatting, static types, and tests as four independent jobs. Reproduce each locally with:

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run ty check              # static types
uv run pytest                # tests
```

> **Repo admin follow-up:** GitHub Actions can only report these checks — it cannot make them required. To actually block merges on a red check, a repo admin must enable **Settings → Branches → Branch protection rules → require a rule for `master` → "Require status checks to pass before merging"** and select `Lint`, `Format`, `Type check`, and `Test`.

## Endpoints

All datetimes must be ISO 8601 **with an offset** (`Z` or `±HH:MM`); they are stored and returned in UTC.

| Method | Path | Description |
| ------ | ---- | ----------- |
| `POST` | `/slots` | Create a slot `{clinician_id, start, end}`. 15–120 min, not in the past, no overlap per clinician (409 includes `conflicting_slot_id`). Returns 201. |
| `GET` | `/slots` | List slots sorted by `start`. Optional filters: `clinician_id`, `date` (`YYYY-MM-DD`, UTC day), `available` (`true`/`false`). |
| `POST` | `/bookings` | Book a slot `{slot_id, patient_name}` (1–100 chars). 404 unknown slot, 409 already booked or started. Returns 201. |
| `GET` | `/bookings/{id}` | Get a booking. 404 if unknown. |
| `POST` | `/bookings/{id}/cancel` | Cancel a booking and free the slot. 409 if already cancelled or less than 24 h before start (exactly 24 h is allowed). Returns 200. |
