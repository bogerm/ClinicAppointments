from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import app, get_now, store

FIXED_NOW = datetime(2030, 1, 1, 8, 0, tzinfo=UTC)


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
def client(clock: Clock) -> Iterator[TestClient]:
    store.reset()
    with TestClient(app) as client:
        yield client
    store.reset()


def iso(dt: datetime) -> str:
    return dt.isoformat()


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def make_slot(
    client: TestClient,
    start: datetime,
    minutes: int = 30,
    clinician_id: str = "dr-1",
) -> dict:
    response = client.post(
        "/slots",
        json={
            "clinician_id": clinician_id,
            "start": iso(start),
            "end": iso(start + timedelta(minutes=minutes)),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_booking(
    client: TestClient, slot_id: str, patient_name: str = "Jane Doe"
) -> dict:
    response = client.post(
        "/bookings", json={"slot_id": slot_id, "patient_name": patient_name}
    )
    assert response.status_code == 201, response.text
    return response.json()
