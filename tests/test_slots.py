from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import (
    FIXED_NOW,
    admin_headers,
    auth_headers,
    make_booking,
    parse,
    register_and_login,
)

T9 = datetime(2030, 1, 1, 9, 0, tzinfo=UTC)


def clinician(client):
    """Register+login a fresh clinician; returns (id, headers)."""
    user, token = register_and_login(client, "clinician")
    return user["id"], auth_headers(token)


def post_slot(client, start, end, headers):
    return client.post("/slots", json={"start": start, "end": end}, headers=headers)


# --- 6.1 create + validation ---


def test_create_slot_returns_201(client):
    dr_id, headers = clinician(client)
    response = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "clinician_id", "start", "end", "booked"}
    assert body["clinician_id"] == dr_id
    assert body["booked"] is False
    assert isinstance(body["id"], str) and body["id"]
    assert parse(body["start"]) == T9


def test_offset_normalized_to_utc(client):
    _, headers = clinician(client)
    response = post_slot(
        client, "2030-01-01T11:00:00+02:00", "2030-01-01T11:30:00+02:00", headers
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
    _, headers = clinician(client)
    assert post_slot(client, start, end, headers).status_code == 422
    assert client.get("/slots").json() == []


def test_missing_field_rejected(client):
    _, headers = clinician(client)
    response = client.post(
        "/slots", json={"start": "2030-01-01T09:00:00Z"}, headers=headers
    )
    assert response.status_code == 422


@pytest.mark.parametrize("end", ["2030-01-01T09:00:00Z", "2030-01-01T08:45:00Z"])
def test_end_not_after_start_rejected(client, end):
    _, headers = clinician(client)
    assert post_slot(client, "2030-01-01T09:00:00Z", end, headers).status_code == 422


@pytest.mark.parametrize(
    ("minutes", "expected"), [(14, 422), (15, 201), (120, 201), (121, 422)]
)
def test_duration_bounds(client, minutes, expected):
    _, headers = clinician(client)
    start = T9 + timedelta(hours=1)
    response = post_slot(
        client,
        start.isoformat(),
        (start + timedelta(minutes=minutes)).isoformat(),
        headers,
    )
    assert response.status_code == expected


def test_past_start_rejected(client):
    _, headers = clinician(client)
    start = FIXED_NOW - timedelta(minutes=1)
    response = post_slot(
        client, start.isoformat(), (start + timedelta(minutes=30)).isoformat(), headers
    )
    assert response.status_code == 422


def test_start_equal_to_now_accepted(client):
    _, headers = clinician(client)
    response = post_slot(
        client,
        FIXED_NOW.isoformat(),
        (FIXED_NOW + timedelta(minutes=30)).isoformat(),
        headers,
    )
    assert response.status_code == 201


def test_unauthenticated_request_rejected(client):
    response = client.post(
        "/slots",
        json={"start": "2030-01-01T09:00:00Z", "end": "2030-01-01T09:30:00Z"},
    )
    assert response.status_code == 401
    assert client.get("/slots").json() == []


def test_patient_forbidden_from_creating_slots(client):
    _, token = register_and_login(client, "patient")
    response = post_slot(
        client,
        "2030-01-01T09:00:00Z",
        "2030-01-01T09:30:00Z",
        auth_headers(token),
    )
    assert response.status_code == 403
    assert client.get("/slots").json() == []


# --- Admin on-behalf-of-clinician (delta spec: "Create a slot") ---


def test_admin_creates_slot_on_behalf_of_clinician(client):
    dr_id, _ = clinician(client)
    headers_admin = admin_headers(client)
    response = client.post(
        "/slots",
        json={
            "clinician_id": dr_id,
            "start": "2030-01-01T09:00:00Z",
            "end": "2030-01-01T09:30:00Z",
        },
        headers=headers_admin,
    )
    assert response.status_code == 201
    assert response.json()["clinician_id"] == dr_id


def test_admin_omitting_clinician_id_rejected(client):
    headers_admin = admin_headers(client)
    response = client.post(
        "/slots",
        json={"start": "2030-01-01T09:00:00Z", "end": "2030-01-01T09:30:00Z"},
        headers=headers_admin,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("bad_id_source", ["unknown", "non-clinician"])
def test_admin_supplied_clinician_id_must_be_valid(client, bad_id_source):
    headers_admin = admin_headers(client)
    if bad_id_source == "unknown":
        clinician_id = "does-not-exist"
    else:
        patient_user, _ = register_and_login(client, "patient")
        clinician_id = patient_user["id"]
    response = client.post(
        "/slots",
        json={
            "clinician_id": clinician_id,
            "start": "2030-01-01T09:00:00Z",
            "end": "2030-01-01T09:30:00Z",
        },
        headers=headers_admin,
    )
    assert response.status_code == 422


# --- 6.1/appointment-slots: overlap ---


def test_overlap_same_clinician_409_names_slot(client):
    _, headers = clinician(client)
    existing_resp = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers
    )
    existing = existing_resp.json()
    response = post_slot(
        client, "2030-01-01T09:15:00Z", "2030-01-01T09:45:00Z", headers
    )
    assert response.status_code == 409
    body = response.json()
    assert body["conflicting_slot_id"] == existing["id"]
    assert existing["id"] in body["detail"]


def test_containing_slot_overlaps(client):
    _, headers = clinician(client)
    existing = post_slot(
        client, "2030-01-01T09:15:00Z", "2030-01-01T09:30:00Z", headers
    ).json()
    response = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T10:00:00Z", headers
    )
    assert response.status_code == 409
    assert response.json()["conflicting_slot_id"] == existing["id"]


def test_identical_slot_overlaps(client):
    _, headers = clinician(client)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers)
    response = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2030-01-01T09:30:00Z", "2030-01-01T10:00:00Z"),
        ("2030-01-01T08:30:00Z", "2030-01-01T09:00:00Z"),
    ],
)
def test_adjacent_slots_do_not_overlap(client, start, end):
    _, headers = clinician(client)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers)
    assert post_slot(client, start, end, headers).status_code == 201


def test_different_clinicians_may_overlap(client):
    _, headers_a = clinician(client)
    _, headers_b = clinician(client)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers_a)
    response = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers_b
    )
    assert response.status_code == 201


def test_overlap_compared_in_utc(client):
    _, headers = clinician(client)
    existing = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers
    ).json()
    response = post_slot(
        client, "2030-01-01T11:00:00+02:00", "2030-01-01T11:30:00+02:00", headers
    )
    assert response.status_code == 409
    assert response.json()["conflicting_slot_id"] == existing["id"]


def test_validation_takes_precedence_over_overlap(client):
    _, headers = clinician(client)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers)
    # Overlaps AND is too short -> 422
    response = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:10:00Z", headers
    )
    assert response.status_code == 422


# --- 6.4 / listing (GET /slots stays public) ---


def test_empty_list(client):
    response = client.get("/slots")
    assert response.status_code == 200
    assert response.json() == []


def test_get_slots_requires_no_auth(client):
    _, headers = clinician(client)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers)
    response = client.get("/slots")  # no Authorization header
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_sorted_by_start(client):
    _, headers = clinician(client)
    for hour in (10, 8, 9):
        start = datetime(2030, 1, 2, hour, tzinfo=UTC)
        post_slot(
            client,
            start.isoformat(),
            (start + timedelta(minutes=30)).isoformat(),
            headers,
        )
    body = client.get("/slots").json()
    assert isinstance(body, list)
    assert [parse(s["start"]).hour for s in body] == [8, 9, 10]


def test_filter_by_clinician(client):
    dr1_id, headers_a = clinician(client)
    _, headers_b = clinician(client)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers_a)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers_b)
    body = client.get("/slots", params={"clinician_id": dr1_id}).json()
    assert [s["clinician_id"] for s in body] == [dr1_id]


def test_filter_by_utc_date(client):
    _, headers = clinician(client)
    # 2030-01-02T01:00+03:00 == 2030-01-01T22:00Z
    response = post_slot(
        client, "2030-01-02T01:00:00+03:00", "2030-01-02T01:30:00+03:00", headers
    )
    slot_id = response.json()["id"]
    start2 = datetime(2030, 1, 2, 9, tzinfo=UTC)
    post_slot(
        client,
        start2.isoformat(),
        (start2 + timedelta(minutes=30)).isoformat(),
        headers,
    )
    day1 = client.get("/slots", params={"date": "2030-01-01"}).json()
    day2 = client.get("/slots", params={"date": "2030-01-02"}).json()
    assert [s["id"] for s in day1] == [slot_id]
    assert slot_id not in [s["id"] for s in day2]
    assert len(day2) == 1


def test_filter_by_availability(client):
    _, headers = clinician(client)
    booked = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers
    ).json()
    free = post_slot(
        client, "2030-01-01T10:00:00Z", "2030-01-01T10:30:00Z", headers
    ).json()
    make_booking(client, booked["id"])
    assert [
        s["id"] for s in client.get("/slots", params={"available": "true"}).json()
    ] == [free["id"]]
    assert [
        s["id"] for s in client.get("/slots", params={"available": "false"}).json()
    ] == [booked["id"]]


def test_combined_filters(client):
    dr1_id, headers_a = clinician(client)
    _, headers_b = clinician(client)
    a = post_slot(
        client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers_a
    ).json()
    post_slot(client, "2030-01-01T10:00:00Z", "2030-01-01T10:30:00Z", headers_a)
    post_slot(client, "2030-01-01T09:00:00Z", "2030-01-01T09:30:00Z", headers_b)
    start_tomorrow = T9 + timedelta(days=1)
    post_slot(
        client,
        start_tomorrow.isoformat(),
        (start_tomorrow + timedelta(minutes=30)).isoformat(),
        headers_a,
    )
    make_booking(client, a["id"])
    body = client.get(
        "/slots",
        params={"clinician_id": dr1_id, "date": "2030-01-01", "available": "true"},
    ).json()
    assert len(body) == 1
    assert parse(body[0]["start"]) == T9 + timedelta(hours=1)


@pytest.mark.parametrize(
    "params", [{"date": "01-01-2030"}, {"date": "2030-13-01"}, {"available": "maybe"}]
)
def test_invalid_query_rejected(client, params):
    assert client.get("/slots", params=params).status_code == 422
