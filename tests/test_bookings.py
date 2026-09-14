from datetime import timedelta

import pytest

from tests.conftest import (
    FIXED_NOW,
    admin_headers,
    auth_headers,
    login,
    make_slot,
    parse,
    register_and_login,
)

PATIENT_PASSWORD = "password123"  # matches register_and_login's default


def slot_by_id(client, slot_id):
    return next(s for s in client.get("/slots").json() if s["id"] == slot_id)


def book_as_new_patient(client, slot_id):
    """Register+login a fresh patient and book `slot_id`. Returns (booking, headers, username)."""
    user, token = register_and_login(client, "patient", password=PATIENT_PASSWORD)
    headers = auth_headers(token)
    response = client.post("/bookings", json={"slot_id": slot_id}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json(), headers, user["username"]


def relogin_headers(client, username):
    """Fresh headers for a patient created by book_as_new_patient — needed after
    advancing the fake clock past the token's 60-minute expiry (see design D7:
    token exp is checked against the same injectable `now` as business rules,
    so a simulated multi-hour time jump also expires the original token, same
    as it would in production)."""
    return auth_headers(login(client, username, PATIENT_PASSWORD))


def cancel(client, booking_id, headers):
    return client.post(f"/bookings/{booking_id}/cancel", headers=headers)


# --- 6.2 create ---


def test_create_booking(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    booking, _, _ = book_as_new_patient(client, slot["id"])
    assert set(booking) == {"id", "slot_id", "patient_id", "status", "created_at"}
    assert booking["slot_id"] == slot["id"]
    assert booking["status"] == "confirmed"
    assert parse(booking["created_at"]) == clock.now
    assert parse(booking["created_at"]).utcoffset() == timedelta(0)
    assert slot_by_id(client, slot["id"])["booked"] is True


def test_invalid_body_precedes_not_found(client):
    _, token = register_and_login(client, "patient")
    response = client.post(
        "/bookings", json={"slot_id": 12345}, headers=auth_headers(token)
    )
    assert response.status_code == 422


def test_unknown_slot(client):
    _, token = register_and_login(client, "patient")
    response = client.post(
        "/bookings",
        json={"slot_id": "does-not-exist"},
        headers=auth_headers(token),
    )
    assert response.status_code == 404


def test_slot_already_booked(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    original, _, _ = book_as_new_patient(client, slot["id"])
    _, other_token = register_and_login(client, "patient")
    response = client.post(
        "/bookings", json={"slot_id": slot["id"]}, headers=auth_headers(other_token)
    )
    assert response.status_code == 409
    assert client.get(
        f"/bookings/{original['id']}", headers=auth_headers(other_token)
    ).status_code in (200, 403)


@pytest.mark.parametrize("elapsed", [timedelta(0), timedelta(minutes=10)])
def test_slot_already_started(client, clock, elapsed):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=1))
    clock.now = FIXED_NOW + timedelta(hours=1) + elapsed
    _, token = register_and_login(client, "patient")
    response = client.post(
        "/bookings", json={"slot_id": slot["id"]}, headers=auth_headers(token)
    )
    assert response.status_code == 409


def test_unauthenticated_request_rejected(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    response = client.post("/bookings", json={"slot_id": slot["id"]})
    assert response.status_code == 401
    assert slot_by_id(client, slot["id"])["booked"] is False


def test_clinician_forbidden_from_booking(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    _, token = register_and_login(client, "clinician")
    response = client.post(
        "/bookings", json={"slot_id": slot["id"]}, headers=auth_headers(token)
    )
    assert response.status_code == 403
    assert slot_by_id(client, slot["id"])["booked"] is False


def test_admin_books_on_behalf_of_patient(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    patient_user, _ = register_and_login(client, "patient")
    response = client.post(
        "/bookings",
        json={"slot_id": slot["id"], "patient_id": patient_user["id"]},
        headers=admin_headers(client),
    )
    assert response.status_code == 201
    assert response.json()["patient_id"] == patient_user["id"]


def test_admin_omitting_patient_id_rejected(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    response = client.post(
        "/bookings", json={"slot_id": slot["id"]}, headers=admin_headers(client)
    )
    assert response.status_code == 422


def test_admin_supplied_patient_id_unknown_rejected(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    response = client.post(
        "/bookings",
        json={"slot_id": slot["id"], "patient_id": "does-not-exist"},
        headers=admin_headers(client),
    )
    assert response.status_code == 422


def test_admin_supplied_patient_id_non_patient_rejected(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    clinician_user, _ = register_and_login(client, "clinician")
    response = client.post(
        "/bookings",
        json={"slot_id": slot["id"], "patient_id": clinician_user["id"]},
        headers=admin_headers(client),
    )
    assert response.status_code == 422


# --- 6.3 get ---


def test_owning_patient_can_get_booking(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    booking, headers, _ = book_as_new_patient(client, slot["id"])
    response = client.get(f"/bookings/{booking['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == booking


def test_admin_can_get_any_booking(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    booking, _, _ = book_as_new_patient(client, slot["id"])
    response = client.get(f"/bookings/{booking['id']}", headers=admin_headers(client))
    assert response.status_code == 200
    assert response.json() == booking


def test_non_owning_patient_forbidden_from_get(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    booking, _, _ = book_as_new_patient(client, slot["id"])
    _, other_token = register_and_login(client, "patient")
    response = client.get(
        f"/bookings/{booking['id']}", headers=auth_headers(other_token)
    )
    assert response.status_code == 403


def test_get_unknown_booking(client):
    _, token = register_and_login(client, "patient")
    response = client.get("/bookings/does-not-exist", headers=auth_headers(token))
    assert response.status_code == 404


def test_get_booking_unauthenticated_rejected(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    booking, _, _ = book_as_new_patient(client, slot["id"])
    response = client.get(f"/bookings/{booking['id']}")
    assert response.status_code == 401


# --- 6.3 cancel ---


def test_cancel_48h_ahead(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, headers, _ = book_as_new_patient(client, slot["id"])
    response = cancel(client, booking["id"], headers)
    assert response.status_code == 200
    assert response.json() == {**booking, "status": "cancelled"}
    assert slot_by_id(client, slot["id"])["booked"] is False
    assert (
        client.get(f"/bookings/{booking['id']}", headers=headers).json()["status"]
        == "cancelled"
    )


def test_admin_can_cancel_any_booking(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, _, _ = book_as_new_patient(client, slot["id"])
    response = cancel(client, booking["id"], admin_headers(client))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_non_owning_patient_forbidden_from_cancel(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, headers, _ = book_as_new_patient(client, slot["id"])
    _, other_token = register_and_login(client, "patient")
    response = cancel(client, booking["id"], auth_headers(other_token))
    assert response.status_code == 403
    assert (
        client.get(f"/bookings/{booking['id']}", headers=headers).json()["status"]
        == "confirmed"
    )


def test_cancel_exactly_24h_ahead(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, _, patient_username = book_as_new_patient(client, slot["id"])
    clock.now = FIXED_NOW + timedelta(hours=24)
    # The original token has expired by now (see relogin_headers docstring).
    headers = relogin_headers(client, patient_username)
    assert cancel(client, booking["id"], headers).status_code == 200


def test_cancel_less_than_24h_ahead(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, _, patient_username = book_as_new_patient(client, slot["id"])
    clock.now = FIXED_NOW + timedelta(hours=24, minutes=1)  # 23h59m before start
    headers = relogin_headers(client, patient_username)
    assert cancel(client, booking["id"], headers).status_code == 409
    assert (
        client.get(f"/bookings/{booking['id']}", headers=headers).json()["status"]
        == "confirmed"
    )
    assert slot_by_id(client, slot["id"])["booked"] is True


def test_cancel_one_microsecond_under_24h(client, clock):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, _, patient_username = book_as_new_patient(client, slot["id"])
    clock.now = FIXED_NOW + timedelta(hours=24, microseconds=1)
    headers = relogin_headers(client, patient_username)
    assert cancel(client, booking["id"], headers).status_code == 409


def test_cancel_twice(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, headers, _ = book_as_new_patient(client, slot["id"])
    assert cancel(client, booking["id"], headers).status_code == 200
    assert cancel(client, booking["id"], headers).status_code == 409


def test_cancel_unknown_booking(client):
    _, token = register_and_login(client, "patient")
    assert cancel(client, "does-not-exist", auth_headers(token)).status_code == 404


def test_cancel_unauthenticated_rejected(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    booking, _, _ = book_as_new_patient(client, slot["id"])
    response = client.post(f"/bookings/{booking['id']}/cancel")
    assert response.status_code == 401


def test_rebook_freed_slot(client):
    slot = make_slot(client, FIXED_NOW + timedelta(hours=48))
    first, first_headers, _ = book_as_new_patient(client, slot["id"])
    cancel(client, first["id"], first_headers)
    second, _, _ = book_as_new_patient(client, slot["id"])
    assert second["id"] != first["id"]
    assert slot_by_id(client, slot["id"])["booked"] is True
    # The old booking stays cancelled and cannot be cancelled again.
    assert cancel(client, first["id"], first_headers).status_code == 409
