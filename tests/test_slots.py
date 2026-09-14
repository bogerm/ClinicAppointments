from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import FIXED_NOW, make_booking, make_slot, parse

T9 = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)


def post_slot(client, start, end, clinician_id="dr-1"):
    return client.post(
        "/slots", json={"clinician_id": clinician_id, "start": start, "end": end}
    )


# --- 3.1 create + validation ---


def test_create_slot_returns_201(client):
    response = post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z")
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "clinician_id", "start", "end", "booked"}
    assert body["clinician_id"] == "dr-1"
    assert body["booked"] is False
    assert isinstance(body["id"], str) and body["id"]
    assert parse(body["start"]) == T9


def test_offset_normalized_to_utc(client):
    response = post_slot(
        client, "2030-01-01T11:00:00+02:00", "2030-01-01T11:30:00+02:00"
    )
    assert response.status_code == 201
    body = response.json()
    assert parse(body["start"]) == T9
    assert parse(body["start"]).utcoffset() == timedelta(0)
    assert parse(body["end"]) == T9 + timedelta(minutes=30)
    assert body["start"].endswith(("Z", "+00:00"))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2030-01-01T09:00:00", "2030-01-01T09:30:00Z"),
        ("2030-01-01T09:00:00Z", "2030-01-01T09:30:00"),
    ],
)
def test_naive_datetime_rejected(client, start, end):
    assert post_slot(client, start, end).status_code == 422
    assert client.get("/slots").json() == []


def test_missing_field_rejected(client):
    response = client.post(
        "/slots", json={"start": "2030-01-01T09:00:00Z", "end": "2030-01-01T09:30:00Z"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("end", ["2030-01-01T09:00:00Z", "2030-01-01T08:45:00Z"])
def test_end_not_after_start_rejected(client, end):
    assert post_slot(client, "2030-01-01T09:00:00Z", end).status_code == 422


@pytest.mark.parametrize(
    ("minutes", "expected"), [(14, 422), (15, 201), (120, 201), (121, 422)]
)
def test_duration_bounds(client, minutes, expected):
    start = T9 + timedelta(hours=1)
    response = post_slot(
        client, start.isoformat(), (start + timedelta(minutes=minutes)).isoformat()
    )
    assert response.status_code == expected


def test_past_start_rejected(client):
    start = FIXED_NOW - timedelta(minutes=1)
    response = post_slot(
        client, start.isoformat(), (start + timedelta(minutes=30)).isoformat()
    )
    assert response.status_code == 422


def test_start_equal_to_now_accepted(client):
    response = post_slot(
        client, FIXED_NOW.isoformat(), (FIXED_NOW + timedelta(minutes=30)).isoformat()
    )
    assert response.status_code == 201


# --- 3.2 overlap ---


def test_overlap_same_clinician_409_names_slot(client):
    existing = make_slot(client, T9, 30)
    response = post_slot(client, "2030-01-01T09:15:00Z", "2030-01-01T09:45:00Z")
    assert response.status_code == 409
    body = response.json()
    assert body["conflicting_slot_id"] == existing["id"]
    assert existing["id"] in body["detail"]


def test_containing_slot_overlaps(client):
    existing = make_slot(client, T9 + timedelta(minutes=15), 15)
    response = post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T10:00:00Z")
    assert response.status_code == 409
    assert response.json()["conflicting_slot_id"] == existing["id"]


def test_identical_slot_overlaps(client):
    make_slot(client, T9, 30)
    assert (
        post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z").status_code
        == 409
    )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2030-01-01T09:30:00Z", "2030-01-01T10:00:00Z"),
        ("2030-01-01T08:30:00Z", "2030-01-01T09:00:00Z"),
    ],
)
def test_adjacent_slots_do_not_overlap(client, start, end):
    make_slot(client, T9, 30)
    assert post_slot(client, start, end).status_code == 201


def test_different_clinicians_may_overlap(client):
    make_slot(client, T9, 30, clinician_id="dr-1")
    assert (
        post_slot(
            client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", clinician_id="dr-2"
        ).status_code
        == 201
    )


def test_overlap_compared_in_utc(client):
    existing = make_slot(client, T9, 30)
    response = post_slot(
        client, "2030-01-01T11:00:00+02:00", "2030-01-01T11:30:00+02:00"
    )
    assert response.status_code == 409
    assert response.json()["conflicting_slot_id"] == existing["id"]


def test_validation_takes_precedence_over_overlap(client):
    make_slot(client, T9, 30)
    # Overlaps AND is too short -> 422
    assert (
        post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:10:00Z").status_code
        == 422
    )


# --- 3.3 listing ---


def test_empty_list(client):
    response = client.get("/slots")
    assert response.status_code == 200
    assert response.json() == []


def test_list_sorted_by_start(client):
    for hour in (10, 8, 9):
        make_slot(
            client, datetime(2030, 1, 2, hour, tzinfo=UTC), clinician_id=f"dr-{hour}"
        )
    body = client.get("/slots").json()
    assert isinstance(body, list)
    assert [parse(s["start"]).hour for s in body] == [8, 9, 10]


def test_filter_by_clinician(client):
    make_slot(client, T9, clinician_id="dr-1")
    make_slot(client, T9, clinician_id="dr-2")
    body = client.get("/slots", params={"clinician_id": "dr-1"}).json()
    assert [s["clinician_id"] for s in body] == ["dr-1"]


def test_filter_by_utc_date(client):
    # 2030-01-02T01:00+03:00 == 2030-01-01T22:00Z
    response = post_slot(
        client, "2030-01-02T01:00:00+03:00", "2030-01-02T01:30:00+03:00"
    )
    slot_id = response.json()["id"]
    make_slot(client, datetime(2030, 1, 2, 9, tzinfo=UTC))
    day1 = client.get("/slots", params={"date": "2030-01-01"}).json()
    day2 = client.get("/slots", params={"date": "2030-01-02"}).json()
    assert [s["id"] for s in day1] == [slot_id]
    assert slot_id not in [s["id"] for s in day2]
    assert len(day2) == 1


def test_filter_by_availability(client):
    booked = make_slot(client, T9)
    free = make_slot(client, T9 + timedelta(hours=1))
    make_booking(client, booked["id"])
    assert [
        s["id"] for s in client.get("/slots", params={"available": "true"}).json()
    ] == [free["id"]]
    assert [
        s["id"] for s in client.get("/slots", params={"available": "false"}).json()
    ] == [booked["id"]]


def test_combined_filters(client):
    a = make_slot(client, T9, clinician_id="dr-1")
    make_slot(client, T9 + timedelta(hours=1), clinician_id="dr-1")
    make_slot(client, T9, clinician_id="dr-2")
    make_slot(client, T9 + timedelta(days=1), clinician_id="dr-1")
    make_booking(client, a["id"])
    body = client.get(
        "/slots",
        params={"clinician_id": "dr-1", "date": "2030-01-01", "available": "true"},
    ).json()
    assert len(body) == 1
    assert parse(body[0]["start"]) == T9 + timedelta(hours=1)


@pytest.mark.parametrize(
    "params", [{"date": "01-01-2030"}, {"date": "2030-13-01"}, {"available": "maybe"}]
)
def test_invalid_query_rejected(client, params):
    assert client.get("/slots", params=params).status_code == 422
