import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import app, get_now, store

FIXED_NOW = datetime(2030, 1, 1, 8, 0, tzinfo=UTC)

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin-password-1"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Iterator[Clock]:
    clock = Clock(FIXED_NOW)
    app.dependency_overrides[get_now] = lambda: clock.now
    yield clock
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env vars the app's lifespan needs, set before the TestClient starts it."""
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-not-for-production")
    monkeypatch.setenv("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)
    monkeypatch.setenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)


@pytest.fixture
def client(clock: Clock, auth_env: None) -> Iterator[TestClient]:
    store.reset()
    with TestClient(app) as client:
        yield client
    store.reset()


def iso(dt: datetime) -> str:
    return dt.isoformat()


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


_username_counter = itertools.count(1)


def register(
    client: TestClient,
    role: str,
    username: str | None = None,
    password: str = "password123",
) -> dict:
    username = username or f"{role}-{next(_username_counter)}"
    response = client.post(
        "/auth/register",
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 201, response.text
    return {**response.json(), "password": password}


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def register_and_login(
    client: TestClient,
    role: str,
    username: str | None = None,
    password: str = "password123",
) -> tuple[dict, str]:
    """Register a fresh account with the given role and log in. Returns
    (user_out_dict, access_token)."""
    user = register(client, role, username=username, password=password)
    token = login(client, user["username"], password)
    return user, token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def admin_headers(client: TestClient) -> dict:
    token = login(client, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
    return auth_headers(token)


def make_slot(
    client: TestClient,
    start: datetime,
    minutes: int = 30,
    headers: dict | None = None,
) -> dict:
    """Create a slot. If `headers` is omitted, registers and logs in a fresh
    clinician and uses their token (their id becomes the slot's clinician_id)."""
    if headers is None:
        _, token = register_and_login(client, "clinician")
        headers = auth_headers(token)
    response = client.post(
        "/slots",
        json={
            "start": iso(start),
            "end": iso(start + timedelta(minutes=minutes)),
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_booking(
    client: TestClient,
    slot_id: str,
    headers: dict | None = None,
) -> dict:
    """Book a slot. If `headers` is omitted, registers and logs in a fresh
    patient and uses their token (their id becomes the booking's patient_id)."""
    if headers is None:
        _, token = register_and_login(client, "patient")
        headers = auth_headers(token)
    response = client.post(
        "/bookings",
        json={"slot_id": slot_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
