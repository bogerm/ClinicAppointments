## Context

See proposal.md - Why. `app.py` is a single-module FastAPI app with an in-memory `Store` (slots, bookings) guarded by a `threading.Lock`, an injectable `get_now()` clock dependency used by tests, and no concept of a user today (`clinician_id` and `patient_name` are trusted, caller-supplied strings). CI (`.github/workflows/ci.yml`, from the `ci-pipeline` capability) already runs Ruff, `ty`, and pytest on every push/PR — this change's tests and any new dev tooling ride on that pipeline unchanged.

## Goals / Non-Goals

**Goals:**
- Reuse the existing `Store`/lock/clock patterns for the new `users` data rather than introducing a second storage mechanism.
- Keep the JWT and password-hashing libraries small, actively maintained, and testable without real wall-clock waits (token expiry must be controllable in tests, like the existing `get_now` pattern).
- Make the "current user" and "require role X" checks reusable FastAPI dependencies so the three protected endpoints (and any future ones) declare their requirement in one line.

**Non-Goals:**
- Password reset / email verification / account deletion — out of scope for this change.
- Refresh tokens or token revocation — a single access token with a fixed expiry is enough for this scope; revocation would need server-side session state, which conflicts with the stateless-JWT choice below.
- Rate limiting or account lockout on failed logins — a real hardening concern, but a separate change.
- Multi-admin or admin self-service — this change seeds exactly one admin (see proposal); adding more admins is future work.

## Decisions

### D1. PyJWT for tokens, `bcrypt` for password hashing (not python-jose / passlib)
Use `pyjwt` (2.14, actively maintained by the `encode` org) to sign/verify HS256 JWTs, and the `bcrypt` package (5.0, actively maintained) directly for password hashing — rather than `python-jose` or `passlib`, both of which have had little to no recent maintenance. Neither replacement adds meaningfully more code: `bcrypt.hashpw`/`bcrypt.checkpw` is a two-function API, and `jwt.encode`/`jwt.decode` mirrors what `python-jose` would have done.
- Token claims: `sub` (user id), `role`, `exp` (expiry). Signing key: `AUTH_SECRET_KEY` env var (required at startup; the app fails to start without it, rather than falling back to a hardcoded default). Algorithm: HS256 (symmetric — no key-pair management needed for a single-process demo app).
- Token lifetime: 60 minutes, fixed (`ACCESS_TOKEN_EXPIRE_MINUTES` constant). No refresh flow (Non-Goals).

### D2. `users` dict on the existing `Store`, one lock, same pattern as slots/bookings
Add `users: dict[str, User]` to the existing `Store` class alongside `slots` and `bookings`, keyed by user id, plus a `username_index: dict[str, str]` (username → id) for `O(1)` uniqueness checks and login lookups. All new read-check-write sequences (register, and any future user mutation) acquire the same `store.lock` already used for slots/bookings — one lock for the whole store keeps the concurrency model simple and matches the existing design (see the original design.md's D6 for the appointment API).
- *Alternative*: a separate `UserStore` with its own lock. Rejected — two locks with no defined ordering between them would be a deadlock risk the moment an operation needs both (e.g., admin actions touching both users and bookings); one lock avoids that class of bug entirely at this scale.

### D3. Auth as FastAPI dependencies, not decorators or middleware
Add `get_current_user(token: str = Depends(oauth2_scheme)) -> User` (raises 401 on any failure: missing header, bad signature, expired) and a dependency factory `require_role(*roles: Role) -> Callable` returning a dependency that calls `get_current_user` and raises 403 if the role doesn't match. Use FastAPI's `OAuth2PasswordBearer(tokenUrl="/auth/login")` as the scheme so `/docs` gets a working "Authorize" button for free. Endpoints declare their requirement inline, e.g. `current: Annotated[User, Depends(require_role("clinician", "admin"))]`.
- *Alternative*: ASGI middleware that inspects every request. Rejected — middleware can't easily express "different roles per route" or integrate with FastAPI's dependency-injected testing/override story (`app.dependency_overrides`), which the test suite already relies on for the clock (see the appointment API's design.md D7).

### D4. Ownership check lives in the route, not the dependency
`require_role("patient", "admin")` only checks role, not resource ownership — the route body still checks `current.role == "admin" or booking.patient_id == current.id` before allowing `GET /bookings/{id}` / cancel, mirroring exactly the 403-vs-404-vs-409 ordering the spec lays out. A generic "owns this resource" dependency was considered but rejected: with only two such endpoints, a shared dependency would need the same lookup the route already does to find the booking (to then also 404), so it wouldn't save the lookup — only add an extra layer to read through.

### D5. Body shape change: role-conditional required field via a validator, not two request models
Rather than two separate Pydantic models for "clinician creates" vs "admin creates on behalf of," `SlotCreate` keeps a single model with `clinician_id: str | None = None`, and the route itself enforces "required for admin, forbidden for clinician" (a plain `if` in the handler, since the rule depends on the authenticated role, which Pydantic validators can't see). Same approach for `BookingCreate.patient_id`. This keeps FastAPI's generated OpenAPI schema simple (one input shape per endpoint) while the role-conditional rule is enforced where the identity is known.
- *Alternative*: `Field(exclude=True)` tricks or two response models keyed by role. Rejected as unneeded complexity for a two-way branch that a single `if` handles clearly.

### D6. Startup admin seed is idempotent and does not block missing config
On FastAPI startup (a `lifespan` handler, replacing the current bare `app = FastAPI(...)`), read `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `AUTH_SECRET_KEY` from the environment. If `AUTH_SECRET_KEY` is missing, raise at startup (no insecure default). If `ADMIN_USERNAME`/`ADMIN_PASSWORD` are missing, log a warning and skip seeding (dev convenience — most local/test runs set all three via a fixture or `.env`, but a missing admin shouldn't crash an otherwise-valid boot). If an admin with that username already exists (re-seeding an already-running process's store — not expected in practice since storage is in-memory and per-process, but relevant for tests that reuse the app object), seeding is a no-op rather than erroring.

### D7. Test-time secret and admin config
Tests set `AUTH_SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` via `monkeypatch.setenv` in a fixture (or a `pytest-dotenv`-free `.env.test` loaded manually) before the `TestClient`'s lifespan runs, keeping the existing `client`/`clock` fixtures in `tests/conftest.py` intact and additive. Token expiry in tests uses the existing overridable `get_now` dependency: `jwt.encode`'s `exp` claim is computed from `get_now() + timedelta(minutes=...)`, not `datetime.now()` directly, so the "expired token" scenario can be tested by advancing the fake clock without sleeping.

## Risks / Trade-offs

- [HS256 with one shared secret means anything that can read `AUTH_SECRET_KEY` can mint valid tokens for any role] → Acceptable for this app's scope (single process, no plugin/extension surface); document the env var as sensitive in the README, matching how `ADMIN_PASSWORD` is already sensitive.
- [No token revocation: a leaked or logged-out token stays valid until its 60-minute expiry] → Accepted per Non-Goals; short expiry bounds the exposure window without adding server-side session state.
- [In-memory `users` means every account — including the seeded admin — disappears on restart, and re-registering after a restart can reuse a now-orphaned booking's `patient_id`] → Same limitation the app already has for slots/bookings (documented in the original design.md); the admin reseed on every startup (D6) at least keeps that one account stable across restarts.
- [Changing `POST /slots` / `POST /bookings` request bodies is a breaking API change for any existing caller] → Called out explicitly in the proposal as **BREAKING**; there's no deployed client yet (this is a fresh project), so the cost is documentation, not migration.
- [Bcrypt hashing is deliberately slow (~100ms/call)] → Fine at this scale (no bulk user operations); would need tuning (lower rounds in tests) only if it made the test suite noticeably slow, which 60 tests plus a handful of new ones will not.

## Migration Plan

No production deployment exists yet (Non-Goal / not applicable — see the `ci-pipeline` capability's design, which also has no deployment target). Rollout is: merge this change, set `AUTH_SECRET_KEY`/`ADMIN_USERNAME`/`ADMIN_PASSWORD` wherever the app is run (documented in the README), and update any manual/API testing scripts to register + log in before calling the now-protected endpoints. Rollback is reverting the commit; no persisted data survives a restart today, so there is no data migration to undo.
