from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from tests.conftest import FIXED_NOW, make_slot


def test_end_to_end_flow(client):
    created = client.post(
        "/slots",
        json={
            "clinician_id": "dr-house",
            "start": (FIXED_NOW + timedelta(days=3)).isoformat(),
            "end": (FIXED_NOW + timedelta(days=3, minutes=45)).isoformat(),
        },
    )
    assert created.status_code == 201
    slot_id = created.json()["id"]

    listed = client.get("/slots", params={"clinician_id": "dr-house", "available": "true"}).json()
    assert [s["id"] for s in listed] == [slot_id]

    booking = client.post("/bookings", json={"slot_id": slot_id, "patient_name": "Jane Doe"})
    assert booking.status_code == 201
    booking_id = booking.json()["id"]
    assert client.get("/slots", params={"available": "true"}).json() == []
    assert client.get(f"/bookings/{booking_id}").json()["status"] == "confirmed"

    cancelled = client.post(f"/bookings/{booking_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    available = client.get("/slots", params={"available": "true"}).json()
    assert [s["id"] for s in available] == [slot_id]

    rebooked = client.post("/bookings", json={"slot_id": slot_id, "patient_name": "John Roe"})
    assert rebooked.status_code == 201
    assert client.get("/slots", params={"available": "false"}).json()[0]["id"] == slot_id


def test_concurrent_bookings_only_one_succeeds(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=2))

    def book(i):
        payload = {"slot_id": slot["id"], "patient_name": f"P{i}"}
        return client.post("/bookings", json=payload).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(book, range(50)))
    assert codes.count(201) == 1
    assert codes.count(409) == 49


def test_concurrent_overlapping_slots_only_one_succeeds(client):
    start = FIXED_NOW + timedelta(days=2)

    def create(i):
        offset = timedelta(minutes=i % 10)
        payload = {
            "clinician_id": "dr-1",
            "start": (start + offset).isoformat(),
            "end": (start + offset + timedelta(minutes=30)).isoformat(),
        }
        return client.post("/slots", json=payload).status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = list(pool.map(create, range(40)))
    assert codes.count(201) == 1
    assert codes.count(409) == 39
