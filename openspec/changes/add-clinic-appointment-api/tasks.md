## 1. Project Setup (uv)

- [x] 1.1 Initialize the uv project at the repo root (`pyproject.toml`, `.python-version` = 3.13, `.gitignore` with `.venv/`, `__pycache__/`, `.pytest_cache/`) and verify `uv sync` succeeds
- [x] 1.2 Add dependencies: `uv add "fastapi[standard]"` and `uv add --dev pytest httpx`; verify `uv.lock` is created and `uv run python -c "import fastapi, httpx, pytest"` succeeds
- [x] 1.3 Add `[tool.fastapi] entrypoint = "app:app"` and pytest config (`testpaths = ["tests"]`) to `pyproject.toml`; create a minimal `app.py` exposing `app = FastAPI()` and verify `uv run python -c "from app import app"` succeeds

## 2. Core Building Blocks

- [x] 2.1 Add a UTC datetime type (`AwareDatetime` + validator converting to UTC) and request/response models `SlotCreate`, `SlotOut`, `BookingCreate` (`patient_name` 1–100 chars), `BookingOut` (`status` literal `confirmed`/`cancelled`); verify with `tests/test_models.py` that naive datetimes fail, offsets normalize to UTC, and name length boundaries hold
- [x] 2.2 Implement the in-memory `Store` (slots/bookings dicts, `threading.Lock`, uuid4 hex ids) with `get_store` dependency and `StoreDep` alias; verify a pytest fixture can reset/override it between tests
- [x] 2.3 Implement `get_now` clock dependency and `NowDep` alias; add a `conftest.py` fixture that overrides it with a settable fixed UTC instant and provides a `TestClient`; verify with a smoke test that the override is used

## 3. Slots Endpoints

- [x] 3.1 Implement `POST /slots` with 201 response: `end > start`, 15–120 min inclusive, and past-start checks returning 422; verify tests for naive datetime, offset normalization, end<=start, 14/15/120/121 minutes, past start
- [x] 3.2 Add per-clinician half-open overlap detection returning 409 with `detail` naming the slot id and `conflicting_slot_id` (custom exception + handler), checked after 422 validations; verify tests for overlap, containment, adjacent 09:00–09:30/09:30–10:00 allowed, different clinicians allowed, and cross-offset overlap
- [x] 3.3 Implement `GET /slots` returning a plain list sorted by `start` with optional `clinician_id`, `date` (UTC day), `available` filters; verify tests for sorting, empty list, each filter, combined filters, UTC day boundary with offset input, and 422 on invalid `date`

## 4. Bookings Endpoints

- [x] 4.1 Implement `POST /bookings` (201, `status: "confirmed"`, UTC `created_at`, marks slot booked) with 404 unknown slot, 409 already booked, 409 already started (`start <= now`); verify tests for each case, name length 422s, and that `GET /slots` shows `booked: true`
- [x] 4.2 Implement `GET /bookings/{id}` returning 200 or 404; verify tests for existing and unknown ids
- [x] 4.3 Implement `POST /bookings/{id}/cancel` returning 200 with the cancelled booking and freeing the slot; 404 unknown, 409 already cancelled, 409 when `start - now < 24h`; verify tests at 48h, exactly 24h (allowed), 23h59m (rejected, state unchanged), double cancel, and rebooking a freed slot

## 5. Integration & Docs

- [x] 5.1 Add an end-to-end test walking through create slot → list → book → get → cancel → rebook, and a concurrency test booking one slot from multiple threads that asserts exactly one 201; verify `uv run pytest` passes fully
- [x] 5.2 Write `README.md` with setup (`uv sync`), run (`uv run fastapi dev`), and test (`uv run pytest`) commands plus a short endpoint summary; verify `uv run fastapi dev` starts and `/docs` lists all five endpoints
