## Why

The API currently has no accounts: `POST /slots` accepts any caller-supplied `clinician_id`, and `POST /bookings` accepts any caller-supplied `patient_name` — anyone can create slots under any clinician's name or view/cancel anyone's booking by guessing an id. There is no way to say "only this clinician can publish their own slots" or "only this patient can cancel their own booking." Authentication and role-based authorization close this gap: identity comes from a verified account instead of an untrusted request field, and each endpoint enforces who is allowed to call it.

## What Changes

- **BREAKING**: Add user accounts with three roles — `clinician`, `patient`, `admin` — authenticated via a self-issued JWT bearer token (`Authorization: Bearer <token>`).
- **BREAKING**: `POST /slots` no longer accepts `clinician_id` in the body. It requires a `clinician` (or `admin`) token, and the slot's `clinician_id` is taken from the authenticated caller (or, for an admin, an explicit `clinician_id` the admin supplies, since an admin manages any clinician's slots).
- **BREAKING**: `POST /bookings` no longer accepts `patient_name` in the body. It requires a `patient` (or `admin`) token, and the booking's patient identity is taken from the authenticated caller.
- **BREAKING**: `GET /bookings/{id}` and `POST /bookings/{id}/cancel` require a token belonging to the booking's own patient, or an `admin`; any other authenticated caller gets 403.
- `GET /slots` stays public (no token required) so anyone can browse availability before creating an account, per the existing `appointment-slots` capability.
- Add `POST /auth/register` (creates a `clinician` or `patient` account; `admin` cannot be self-registered) and `POST /auth/login` (returns a bearer token) endpoints.
- Seed exactly one built-in `admin` account at process startup from environment variables, so an admin always exists without any open self-service admin signup.
- Add a JWT library and a password-hashing library as runtime dependencies (exact packages chosen in design.md).

## Capabilities

### New Capabilities
- `auth`: Account registration, login, password hashing, JWT issuance/verification, and role-based access control (`clinician` / `patient` / `admin`) enforced across the API.

### Modified Capabilities
- `appointment-slots`: `POST /slots` requires a `clinician` or `admin` token instead of a caller-supplied `clinician_id`; `clinician_id` in the request/response now reflects the authenticated clinician (or the admin-specified one). `GET /slots` requirements are unchanged (stays public).
- `appointment-bookings`: `POST /bookings` requires a `patient` or `admin` token instead of a caller-supplied `patient_name`; the booking's patient identity comes from the account. `GET /bookings/{id}` and `POST /bookings/{id}/cancel` add an ownership/role check (403 if the caller is neither the booking's own patient nor an admin) on top of their existing 404/409 rules.

## Impact

- **New files**: `specs/auth` capability; new auth module(s) in the application (users store, password hashing, JWT issuance/verification, dependency for "current user" and role checks).
- **Modified files**: `app.py` — `SlotCreate`/`BookingCreate` request models drop `clinician_id` / `patient_name`; the three protected endpoints gain an auth dependency and role/ownership checks.
- **Dependencies**: adds a JWT library and a password-hashing library (see design.md for the specific packages and rationale).
- **Breaking API changes**: existing clients of `POST /slots` and `POST /bookings` must switch from passing `clinician_id`/`patient_name` in the body to sending a bearer token obtained from `POST /auth/login`. `GET /bookings/{id}` and cancel now return 403 for a non-owning, non-admin caller where they previously allowed any caller.
- **Storage**: users are stored in-memory (a new `users` dict on the existing in-memory `Store`), consistent with the rest of the app; no accounts survive a restart except the environment-seeded admin, which is re-seeded identically on every startup.
- **Assumptions recorded for the specs** (decided via clarifying questions in this session, not stated in the original brief): three roles (clinician/patient/admin); identity is tied to the logged-in account (breaking change) rather than kept as free-text fields; JWT bearer tokens (stateless, self-issued) rather than opaque server-side sessions; `GET /slots` stays public; exactly one admin is seeded from environment variables at startup, with no self-service admin registration or role-promotion endpoint in this change (an admin is created only via the startup seed).
