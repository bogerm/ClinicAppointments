from datetime import timedelta

import pytest

from tests.conftest import FIXED_NOW, make_booking, make_slot, parse


def slot_by_id(client, slot_id):
    return next(s for s in client.get("/slots").json() if s["id"] == slot_id)


def cancel(client, booking_id):
    return client.post(f"/bookings/{booking_id}/cancel")


# --- 4.1 create ---


def test_create_booking(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    response = client.post(
        "/bookings", json={"slot_id": slot["id"], "patient_name": "Jane Doe"}
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "slot_id", "patient_name", "status", "created_at"}
    assert body["slot_id"] == slot["id"]
    assert body["patient_name"] == "Jane Doe"
    assert body["status"] == "confirmed"
    assert parse(body["created_at"]) == clock.now
    assert parse(body["created_at"]).utcoffset() == timedelta(0)
    assert slot_by_id(client, slot["id"])["booked"] is True


@pytest.mark.parametrize("name", ["J", "x" * 100])
def test_patient_name_boundaries(client, name):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    response = client.post(
        "/bookings", json={"slot_id": slot["id"], "patient_name": name}
    )
    assert response.status_code == 201


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_invalid_patient_name(client, name):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    response = client.post(
        "/bookings", json={"slot_id": slot["id"], "patient_name": name}
    )
    assert response.status_code == 422
    assert slot_by_id(client, slot["id"])["booked"] is False


def test_invalid_body_precedes_not_found(client):
    response = client.post("/bookings", json={"slot_id": "nope", "patient_name": ""})
    assert response.status_code == 422


def test_unknown_slot(client):
    response = client.post(
        "/bookings", json={"slot_id": "does-not-exist", "patient_name": "Jane"}
    )
    assert response.status_code == 404


def test_slot_already_booked(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    original = make_booking(client, slot["id"])
    response = client.post(
        "/bookings", json={"slot_id": slot["id"], "patient_name": "Other"}
    )
    assert response.status_code == 409
    assert client.get(f"/bookings/{original['id']}").json() == original


@pytest.mark.parametrize("elapsed", [timedelta(0), timedelta(minutes=10)])
def test_slot_already_started(client, clock, elapsed):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=1))
    clock.now = FIXED_NOW + timedelta(hours=1) + elapsed
    response = client.post(
        "/bookings", json={"slot_id": slot["id"], "patient_name": "Jane"}
    )
    assert response.status_code == 409


# --- 4.2 get ---


def test_get_booking(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    booking = make_booking(client, slot["id"])
    response = client.get(f"/bookings/{booking['id']}")
    assert response.status_code == 200
    assert response.json() == booking


def test_get_unknown_booking(client):
    assert client.get("/bookings/does-not-exist").status_code == 404


# --- 4.3 cancel ---


def test_cancel_48h_ahead(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking = make_booking(client, slot["id"])
    response = cancel(client, booking["id"])
    assert response.status_code == 200
    assert response.json() == {**booking, "status": "cancelled"}
    assert slot_by_id(client, slot["id"])["booked"] is False
    assert client.get(f"/bookings/{booking['id']}").json()["status"] == "cancelled"


def test_cancel_exactly_24h_ahead(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking = make_booking(client, slot["id"])
    clock.now = FIXED_NOW + timedelta(hours=24)
    assert cancel(client, booking["id"]).status_code == 200


def test_cancel_less_than_24h_ahead(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking = make_booking(client, slot["id"])
    clock.now = FIXED_NOW + timedelta(hours=24, minutes=1)  # 23h59m before start
    assert cancel(client, booking["id"]).status_code == 409
    assert client.get(f"/bookings/{booking['id']}").json()["status"] == "confirmed"
    assert slot_by_id(client, slot["id"])["booked"] is True


def test_cancel_one_microsecond_under_24h(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking = make_booking(client, slot["id"])
    clock.now = FIXED_NOW + timedelta(hours=24, microseconds=1)
    assert cancel(client, booking["id"]).status_code == 409


def test_cancel_twice(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking = make_booking(client, slot["id"])
    assert cancel(client, booking["id"]).status_code == 200
    assert cancel(client, booking["id"]).status_code == 409


def test_cancel_unknown_booking(client):
    assert cancel(client, "does-not-exist").status_code == 404


def test_rebook_freed_slot(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    first = make_booking(client, slot["id"])
    cancel(client, first["id"])
    second = make_booking(client, slot["id"], patient_name="John Roe")
    assert second["id"] != first["id"]
    assert slot_by_id(client, slot["id"])["booked"] is True
    # The old booking stays cancelled and cannot be cancelled again.
    assert cancel(client, first["id"]).status_code == 409
