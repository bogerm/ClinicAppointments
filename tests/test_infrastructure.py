from datetime import timedelta

from app import store
from tests.conftest import FIXED_NOW, auth_headers, make_slot, register_and_login


def test_clock_override_is_used(client, clock):
    # A slot one minute after the fixed clock is "future" only if the override is active.
    make_slot(client, FIXED_NOW + timedelta(minutes=1))
    clock.advance(timedelta(hours=1))
    _, token = register_and_login(client, "clinician")
    response = client.post(
        "/slots",
        json={
            "start": (FIXED_NOW + timedelta(minutes=30)).isoformat(),
            "end": (FIXED_NOW + timedelta(minutes=60)).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 422


def test_store_is_reset_between_tests_part1(client):
    make_slot(client, FIXED_NOW + timedelta(hours=1))
    assert len(store.slots) == 1


def test_store_is_reset_between_tests_part2(client):
    assert store.slots == {}
    assert client.get("/slots").json() == []
