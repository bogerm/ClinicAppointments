from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from tests.conftest import (
    FIXED_NOW,
    auth_headers,
    make_slot,
    register_and_login,
)


def test_end_to_end_flow(client):
    _, clinician_token = register_and_login(client, "clinician")
    clinician_hdrs = auth_headers(clinician_token)
    created = client.post(
        "/slots",
        json={
            "start": (FIXED_NOW + timedelta(days=3)).isoformat(),
            "end": (FIXED_NOW + timedelta(days=3, minutes=45)).isoformat(),
        },
        headers=clinician_hdrs,
    )
    assert created.status_code == 201
    slot = created.json()
    slot_id = slot["id"]

    listed = client.get(
        "/slots", params={"clinician_id": slot["clinician_id"], "available": "true"}
    ).json()
    assert [s["id"] for s in listed] == [slot_id]

    patient_user, patient_token = register_and_login(client, "patient")
    patient_hdrs = auth_headers(patient_token)
    booking = client.post("/bookings", json={"slot_id": slot_id}, headers=patient_hdrs)
    assert booking.status_code == 201
    booking_id = booking.json()["id"]
    assert booking.json()["patient_id"] == patient_user["id"]
    assert client.get("/slots", params={"available": "true"}).json() == []
    assert (
        client.get(f"/bookings/{booking_id}", headers=patient_hdrs).json()["status"]
        == "confirmed"
    )

    cancelled = client.post(f"/bookings/{booking_id}/cancel", headers=patient_hdrs)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    available = client.get("/slots", params={"available": "true"}).json()
    assert [s["id"] for s in available] == [slot_id]

    _, other_patient_token = register_and_login(client, "patient")
    rebooked = client.post(
        "/bookings",
        json={"slot_id": slot_id},
        headers=auth_headers(other_patient_token),
    )
    assert rebooked.status_code == 201
    assert (
        client.get("/slots", params={"available": "false"}).json()[0]["id"] == slot_id
    )


def test_concurrent_bookings_only_one_succeeds(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))
    # All requests race as the same patient (a realistic double-click/retry
    # scenario) — the slot-already-booked check doesn't depend on identity.
    _, token = register_and_login(client, "patient")
    headers = auth_headers(token)

    def book(_i):
        payload = {"slot_id": slot["id"]}
        return client.post("/bookings", json=payload, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(book, range(50)))
    assert codes.count(201) == 1
    assert codes.count(409) == 49


def test_concurrent_overlapping_slots_only_one_succeeds(client):
    start = FIXED_NOW + timedelta(days=2)
    _, token = register_and_login(client, "clinician")
    headers = auth_headers(token)

    def create(i):
        offset = timedelta(minutes=i % 10)
        payload = {
            "start": (start + offset).isoformat(),
            "end": (start + offset + timedelta(minutes=30)).isoformat(),
        }
        return client.post("/slots", json=payload, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(create, range(40)))
    assert codes.count(201) == 1
    assert codes.count(409) == 39
