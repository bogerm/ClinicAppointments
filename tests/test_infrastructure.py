from datetime import timedelta

from app import store
from tests.conftest import FIXED_NOW, make_slot


def test_clock_override_is_used(client, clock):
    # A slot one minute after the fixed clock is "future" only if the override is active.
    make_slot(client, FIXED_NOW + timedelta(minutes=1))
    clock.advance(timedelta(hours=1))
    response = client.post(
        "/slots",
        json={
            "clinician_id": "dr-2",
            "start": (FIXED_NOW + timedelta(minutes=30)).isoformat(),
            "end": (FIXED_NOW + timedelta(minutes=60)).isoformat(),
        },
    )
    assert response.status_code == 422


def test_store_is_reset_between_tests_part1(client):
    make_slot(client, FIXED_NOW + timedelta(hours=1))
    assert len(store.slots) == 1


def test_store_is_reset_between_tests_part2(client):
    assert store.slots == {}
    assert client.get("/slots").json() == []
