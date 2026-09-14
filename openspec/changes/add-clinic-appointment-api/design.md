## Context

Greenfield repository: only `openspec/` exists. Requirements come from `openspec/specs/PROBLEM.md` (see proposal.md - Why) and are formalized in `specs/appointment-slots/spec.md` and `specs/appointment-bookings/spec.md`. Hard constraints from the brief: FastAPI, an app object named `app` in `app.py`, in-memory storage, UTC everywhere. Tooling constraint from the request: `uv` for project and dependency management. Local toolchain: uv 0.11, Python 3.13.

## Goals / Non-Goals

**Goals:**
- A single importable module `app.py` (`from app import app`) that satisfies every scenario in the specs.
- Deterministic tests for time-dependent rules (past start, already started, exact 24h boundary).
- Correct behaviour under concurrent requests within one process (no double booking, no overlapping slots).

**Non-Goals:**
- Persistence, multi-process/multi-worker consistency, authentication/authorization, pagination, slot deletion or editing.

## Decisions

### D1. Project layout and tooling with uv
`uv init --app` style project at the repo root: `pyproject.toml` (requires-python `>=3.12`), `.python-version` (3.13), `uv.lock`. Runtime dependency `fastapi[standard]` (brings uvicorn and the `fastapi` CLI); dev group (`uv add --dev`) `pytest` and `httpx` (needed by `fastapi.testclient`). Declare `[tool.fastapi] entrypoint = "app:app"` so `uv run fastapi dev` works. Tests live in `tests/`; run with `uv run pytest`.
- *Alternative*: package layout (`src/clinic/...`). Rejected — the brief mandates `app.py`, and the domain is small enough for one module.

### D2. Single module `app.py` with clear sections
`app.py` contains: Pydantic request/response models, the in-memory store, a clock dependency, and path operations. Keeping everything in one file matches the brief; sections are ordered models → store → dependencies → routes. If it grows past ~300 lines, the store can be split into a sibling module without changing the `app.py` entrypoint.

### D3. Datetime handling via Pydantic `AwareDatetime`
Request fields `start`/`end` are typed `pydantic.AwareDatetime`, so naive values fail validation and FastAPI returns 422 automatically. An `AfterValidator` converts values to `timezone.utc`. Response models use the same UTC datetimes; Pydantic v2 serializes UTC as `...Z`, satisfying "return UTC with an explicit designator".
- *Alternative*: plain `datetime` plus manual `tzinfo is None` checks. Rejected — more code, and error format would diverge from FastAPI's standard 422 body.

### D4. Validation layering and status codes
- Shape/format errors (missing fields, naive datetimes, `patient_name` length via `Field(min_length=1, max_length=100)`, bad `date`/`available` query values) → FastAPI's built-in 422.
- Cross-field and clock-based slot rules (`end > start`, 15–120 min inclusive, `start >= now`) are checked in the route handler (not a model validator) because "past" depends on the injectable clock; failures raise `HTTPException(422, detail=...)`.
- Business conflicts → `HTTPException(409)`; missing entities → `HTTPException(404)`.
- Order: 422 checks run before 404/409 checks, as stated in the specs.

### D5. Overlap conflict response names the slot id
Overlap check per clinician: `new.start < existing.end and existing.start < new.end` (half-open intervals, so touching endpoints do not conflict). The 409 body is `{"detail": "Slot overlaps existing slot <id>", "conflicting_slot_id": "<id>"}` — the id appears both in the human-readable `detail` (compatible with clients that only read `detail`) and as a dedicated machine-readable field. Implemented with a small custom exception + exception handler, so other errors keep the standard `{"detail": ...}` shape. If several slots conflict, the earliest-starting one is reported.

### D6. In-memory store guarded by a lock
A `Store` class holds `slots: dict[str, Slot]` and `bookings: dict[str, Booking]`. `booked` is stored on the slot and flipped on booking/cancellation (simpler and O(1) for listing vs. deriving from bookings). Every read-check-write sequence (create slot, book, cancel) runs under one `threading.Lock`, because path operations are plain `def` functions executed in FastAPI's threadpool and races would allow double booking or overlapping slots. IDs are `uuid4().hex` strings. Overlap search is a linear scan over that clinician's slots — adequate for in-memory scale.
- The store is exposed via a dependency (`StoreDep = Annotated[Store, Depends(get_store)]`) backed by a module-level instance; tests override it (or reset it) per test for isolation.
- *Alternative*: `async def` routes with no lock (single event loop thread). Rejected — relies on never adding an `await` in the critical section; the lock makes the invariant explicit.

### D7. Injectable clock
A dependency `get_now() -> datetime` returns `datetime.now(timezone.utc)`; routes take `NowDep`. Tests override it via `app.dependency_overrides` with a fixed instant, making "exactly 24 hours" and "already started" scenarios exact. All comparisons use the single `now` captured per request.
- Cancellation rule: reject when `slot.start - now < timedelta(hours=24)`; equality passes.
- Booking rule: reject when `slot.start <= now` (already started).
- Slot creation rule: reject when `slot.start < now` (past).

### D8. `GET /slots` filters
Query params: `clinician_id: str | None`, `date: datetime.date | None` (FastAPI parses `YYYY-MM-DD`, invalid → 422), `available: bool | None`. Date match uses `slot.start.date()` on the UTC value. Results sorted by `(start, id)` for stable ordering; response type `list[SlotOut]` (plain array, no envelope).

### D9. Cancellation response
`POST /bookings/{id}/cancel` returns 200 with the updated booking object — the brief doesn't specify a body, and returning the resource is the most useful and consistent choice.

## Risks / Trade-offs

- [Data lost on restart; state not shared across multiple uvicorn workers] → Accepted per brief; README documents running a single worker.
- [Wall-clock tests are flaky around boundaries] → All time-sensitive tests use the overridden clock (D7).
- [Pydantic's `Z` vs `+00:00` serialization might not match a client that string-compares] → Specs require UTC with an explicit designator, not a specific spelling; tests parse datetimes before comparing.
- [Linear overlap scan is O(n) per clinician] → Fine for in-memory scale; an interval index can be added later without spec changes.
- [Global lock serializes writes] → Negligible for an in-memory demo service.

## Migration Plan

None — new service with no existing deployment or data.
