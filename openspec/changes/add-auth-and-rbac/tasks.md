## 1. Dependencies and Configuration

- [x] 1.1 Run `uv add pyjwt bcrypt` and verify `pyproject.toml`/`uv.lock` are updated and `uv run python -c "import jwt, bcrypt"` succeeds
- [x] 1.2 Add `AUTH_SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` to a documented `.env.example` (not committed as real secrets) and to the README's setup section; verify the app raises a clear startup error when `AUTH_SECRET_KEY` is unset

## 2. User Model and Store

- [x] 2.1 Add a `Role` literal (`"clinician" | "patient" | "admin"`) and a `User` model (`id`, `username`, `role`, `password_hash`) plus request/response models (`RegisterRequest`, `UserOut`, `LoginRequest`, `TokenOut`); verify with unit tests that `RegisterRequest` rejects `role="admin"`, a password under 8 chars, and that `UserOut`/`TokenOut` never include `password_hash`
- [x] 2.2 Add `users: dict[str, User]` and `username_index: dict[str, str]` to `Store`, written only under the existing `store.lock`; verify a test can register two distinct usernames and gets 409 on a repeat

## 3. Password Hashing and JWT Helpers

- [x] 3.1 Add `hash_password`/`verify_password` wrapping `bcrypt`; verify a unit test round-trips a password and rejects a wrong one
- [x] 3.2 Add `create_access_token(user, now)` and `decode_access_token(token, now)` wrapping `pyjwt`, with `exp` computed from the passed-in `now` (not wall-clock) per design D7; verify unit tests for a valid token, a tampered/invalid-signature token, and an expired token (using a fixed `now` and a `now` advanced past expiry)

## 4. Auth Endpoints

- [x] 4.1 Implement `POST /auth/register`: creates a `clinician` or `patient` account, hashes the password, respond 201 with `{id, username, role}`; verify tests for successful clinician/patient registration, duplicate username (409), short password (422), and `role="admin"` (422)
- [x] 4.2 Implement `POST /auth/login`: verifies credentials, returns `{access_token, token_type: "bearer"}`; verify tests for success, wrong password (401), and unknown username (401)
- [x] 4.3 Implement the startup `lifespan` handler seeding exactly one admin from `ADMIN_USERNAME`/`ADMIN_PASSWORD` (skip with a warning if unset, no-op if already seeded per design D6); verify a test that the seeded admin can log in and gets a token with role `admin`

## 5. Auth Dependencies (Current User, Role Checks)

- [x] 5.1 Implement `get_current_user` (via `OAuth2PasswordBearer(tokenUrl="/auth/login")`) raising 401 for missing/malformed/invalid-signature/expired tokens; verify unit tests for each of those four cases
- [x] 5.2 Implement `require_role(*roles)` dependency factory raising 403 when the authenticated user's role isn't in `roles` (admin is not automatically added — pass it explicitly per design D3's usage, e.g. `require_role("clinician", "admin")`); verify a test that a `patient` gets 403 and a `clinician` gets through on a route requiring `("clinician", "admin")`

## 6. Protect and Update Slots/Bookings Endpoints

- [x] 6.1 Update `SlotCreate` to make `clinician_id` optional; update `POST /slots` to require `require_role("clinician", "admin")`, take `clinician_id` from the authenticated user when `role == "clinician"`, and when `role == "admin"` require the body's `clinician_id` (422 if missing) and validate it identifies an existing account with role `clinician` (422 otherwise); verify tests for: clinician creates own slot (id from token, not body), admin creates on behalf of a given clinician, admin omitting `clinician_id` (422), admin-supplied `clinician_id` unknown or non-clinician (422), unauthenticated (401), patient (403) — all per the `appointment-slots` delta spec
- [x] 6.2 Update `BookingCreate` to make `patient_id` optional (replacing `patient_name`); update `POST /bookings` to require `require_role("patient", "admin")` with the same caller-vs-admin-supplied-id split and existing-account/role validation as 6.1; verify tests for: patient books for self, admin books on behalf of a given patient, admin omitting `patient_id` (422), admin-supplied `patient_id` unknown or non-patient (422), unauthenticated (401), clinician (403) — per the `appointment-bookings` delta spec
- [x] 6.3 Update `GET /bookings/{id}` and `POST /bookings/{id}/cancel` to require `get_current_user` and add the ownership check (`current.role == "admin" or booking.patient_id == current.id`, else 403), preserving existing 404/409 ordering; verify tests for owning-patient access/cancel, admin access/cancel, non-owning-patient 403, and unauthenticated 401 on both endpoints
- [x] 6.4 Confirm `GET /slots` remains unauthenticated (no dependency added); verify a test that it still returns 200 with no `Authorization` header

## 7. Update Existing Tests and Fixtures

- [x] 7.1 Add `tests/conftest.py` fixtures: an env-var fixture setting `AUTH_SECRET_KEY`/`ADMIN_USERNAME`/`ADMIN_PASSWORD` before the app's lifespan runs, and helper functions `register_and_login(client, role)` / `auth_headers(token)`; verify existing fixtures (`client`, `clock`) still work unchanged
- [x] 7.2 Update every existing test in `tests/test_slots.py` and `tests/test_bookings.py` that posts to `POST /slots` or `POST /bookings` to register/log in the right role and send the bearer token instead of a raw `clinician_id`/`patient_name`; verify `uv run pytest` passes with zero regressions in existing scenario coverage (counts may shift as bodies change, but no existing behavior scenario is dropped)
- [x] 7.3 Update `tests/test_integration.py`'s end-to-end and concurrency tests to authenticate as the appropriate role at each step; verify the full flow (create slot → list → book → get → cancel → rebook) and both concurrency tests still pass with tokens in place of raw ids

## 8. Documentation

- [x] 8.1 Update `README.md`: document the three roles, the new `/auth/register` and `/auth/login` endpoints, the required environment variables, and an example `curl` flow (register → login → use the token on `POST /slots`/`POST /bookings`); verify the documented example runs successfully against a locally started server
