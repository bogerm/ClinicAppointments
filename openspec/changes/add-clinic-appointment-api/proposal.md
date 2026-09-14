## Why

Clinicians need a way to publish bookable time slots and patients need a way to reserve and cancel them. The repository is currently empty apart from the brief in `openspec/specs/PROBLEM.md`, so this change delivers the first working version of the Clinic Appointment Booking API as a FastAPI service managed with `uv`.

## What Changes

- Bootstrap a new Python project managed with `uv` (`pyproject.toml`, `uv.lock`), with FastAPI as the runtime dependency and pytest + HTTPX as dev dependencies.
- Add a FastAPI application object named `app` in `app.py` at the repository root.
- Add in-memory storage for slots and bookings (data is lost on restart; no database).
- Add `POST /slots` and `GET /slots` for clinicians to publish slots and for anyone to list/filter them.
- Add `POST /bookings`, `GET /bookings/{id}`, and `POST /bookings/{id}/cancel` for patients to book, look up, and cancel appointments.
- Enforce datetime rules across the API: input must be ISO 8601 with an explicit UTC offset; all values are stored and returned in UTC.
- Add an automated test suite covering every rule in the brief, including boundary cases (15/120-minute durations, back-to-back slots, exactly-24h cancellation).

## Capabilities

### New Capabilities
- `appointment-slots`: Publishing clinician time slots (validation of offsets, duration, past start, per-clinician non-overlap) and listing slots with filters by clinician, UTC date, and availability.
- `appointment-bookings`: Booking a slot for a patient, retrieving a booking, and cancelling it under the 24-hour rule, including the effect on the slot's `booked` flag.

### Modified Capabilities
<!-- None: no existing capability specs in openspec/specs/. -->

## Impact

- **New code**: `app.py` (application, models, in-memory store), `tests/` (pytest suite).
- **New project files**: `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `README.md` with run/test commands.
- **Dependencies**: `fastapi[standard]` (runtime + `fastapi` CLI); dev group `pytest`, `httpx`.
- **APIs**: five new HTTP endpoints as listed above; no existing APIs affected.
- **Assumptions recorded for the specs** (brief is silent on these): IDs are opaque strings; validation errors (422) are checked before conflicts (409); duration limits of 15 and 120 minutes are inclusive; cancelling an unknown booking returns 404; a cancelled slot can be booked again.
