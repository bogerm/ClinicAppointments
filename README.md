# Clinic Appointment Booking API

Clinicians publish time slots, patients book them. Built with FastAPI, managed with [uv](https://docs.astral.sh/uv/).
Storage is in-memory: data is lost on restart and is not shared between workers, so run a single worker.

Authentication is via self-issued JWT bearer tokens, with three roles: **clinician**, **patient**, **admin**. See [Authentication & Roles](#authentication--roles) below.

## Setup

```bash
uv sync
cp .env.example .env   # then edit AUTH_SECRET_KEY / ADMIN_USERNAME / ADMIN_PASSWORD
set -a && source .env && set +a   # export them into the shell before running the app
```

`AUTH_SECRET_KEY` is required — the app refuses to start without it. `ADMIN_USERNAME`/`ADMIN_PASSWORD` are optional; if unset, no admin account is seeded (a warning is logged) and only self-service clinician/patient registration is available. The app reads these from the environment directly (no automatic `.env` loading), so export them however suits your shell.

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

## Authentication & Roles

Three roles: **clinician** (publishes their own slots), **patient** (books/cancels their own appointments), **admin** (can act on behalf of any clinician or patient; seeded at startup, not self-registerable).

Register, log in, and use the returned bearer token on protected endpoints:

```bash
# 1. Register a clinician account
curl -s -X POST http://127.0.0.1:8000/auth/register \
  -H 'content-type: application/json' \
  -d '{"username": "dr-jones", "password": "a-strong-password", "role": "clinician"}'

# 2. Log in to get a token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"username": "dr-jones", "password": "a-strong-password"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# 3. Use the token to create a slot (clinician_id is taken from the token, not the body)
curl -s -X POST http://127.0.0.1:8000/slots \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"start": "2030-01-01T09:00:00Z", "end": "2030-01-01T09:30:00Z"}'
```

A `patient` follows the same register/login flow, then `POST /bookings` with `{"slot_id": "..."}` (no `patient_id` needed — taken from their token). An `admin` may supply an explicit `clinician_id`/`patient_id` in the body to act on someone else's behalf.

`GET /slots` requires no token (public browsing). Every other endpoint requires `Authorization: Bearer <token>`.

## Endpoints

All datetimes must be ISO 8601 **with an offset** (`Z` or `±HH:MM`); they are stored and returned in UTC.

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| `POST` | `/auth/register` | none | Register `{username, password, role}` (`role` is `clinician` or `patient`; `admin` cannot self-register). 409 duplicate username, 422 invalid input. Returns 201. |
| `POST` | `/auth/login` | none | Log in `{username, password}` → `{access_token, token_type}`. 401 on bad credentials. |
| `POST` | `/slots` | clinician or admin | Create a slot `{start, end}` (clinician; `clinician_id` from the token) or `{clinician_id, start, end}` (admin, on behalf of that clinician). 15–120 min, not in the past, no overlap per clinician (409 includes `conflicting_slot_id`). 422 if an admin omits/misreferences `clinician_id`. Returns 201. |
| `GET` | `/slots` | none (public) | List slots sorted by `start`. Optional filters: `clinician_id`, `date` (`YYYY-MM-DD`, UTC day), `available` (`true`/`false`). |
| `POST` | `/bookings` | patient or admin | Book a slot `{slot_id}` (patient; `patient_id` from the token) or `{slot_id, patient_id}` (admin, on behalf of that patient). 404 unknown slot, 409 already booked or started, 422 if an admin omits/misreferences `patient_id`. Returns 201. |
| `GET` | `/bookings/{id}` | owning patient or admin | Get a booking. 403 if authenticated as someone else, 404 if unknown. |
| `POST` | `/bookings/{id}/cancel` | owning patient or admin | Cancel a booking and free the slot. 403 if not the owner/admin, 409 if already cancelled or less than 24 h before start (exactly 24 h is allowed), 404 if unknown. Returns 200. |
