from datetime import timedelta

import pytest

from tests.conftest import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    FIXED_NOW,
    auth_headers,
    login,
    make_slot,
    register,
    register_and_login,
)

# --- 4.1 register ---


def test_register_clinician(client):
    response = client.post(
        "/auth/register",
        json={"username": "dr-1", "password": "password123", "role": "clinician"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "username": "dr-1", "role": "clinician"}
    assert "password" not in body
    assert "password_hash" not in body


def test_register_patient(client):
    response = client.post(
        "/auth/register",
        json={"username": "pat-1", "password": "password123", "role": "patient"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "patient"


def test_register_duplicate_username_rejected(client):
    register(client, "patient", username="dupe")
    response = client.post(
        "/auth/register",
        json={"username": "dupe", "password": "password123", "role": "clinician"},
    )
    assert response.status_code == 409


def test_register_password_too_short_rejected(client):
    response = client.post(
        "/auth/register",
        json={"username": "dr-2", "password": "short1", "role": "clinician"},
    )
    assert response.status_code == 422


def test_register_admin_role_rejected(client):
    response = client.post(
        "/auth/register",
        json={"username": "sneaky", "password": "password123", "role": "admin"},
    )
    assert response.status_code == 422


# --- 4.2 login ---


def test_login_success(client):
    register(client, "patient", username="pat-2", password="password123")
    response = client.post(
        "/auth/login", json={"username": "pat-2", "password": "password123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_rejected(client):
    register(client, "patient", username="pat-3", password="password123")
    response = client.post(
        "/auth/login", json={"username": "pat-3", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_unknown_username_rejected(client):
    response = client.post(
        "/auth/login", json={"username": "does-not-exist", "password": "whatever"}
    )
    assert response.status_code == 401


# --- 4.3 seeded admin ---


def test_seeded_admin_can_log_in(client):
    token = login(client, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD)
    # Use the token on an admin-only-ish action to confirm role is "admin":
    # a clinician-or-admin-gated endpoint must accept it.
    response = client.post(
        "/slots",
        json={
            "clinician_id": None,
            "start": (FIXED_NOW + timedelta(days=1)).isoformat(),
            "end": (FIXED_NOW + timedelta(days=1, minutes=30)).isoformat(),
        },
        headers=auth_headers(token),
    )
    # admin without clinician_id is 422 (not 403), proving role == admin was accepted
    assert response.status_code == 422


# --- 5.1 get_current_user ---


def test_missing_token_rejected(client):
    response = client.post(
        "/slots",
        json={
            "start": (FIXED_NOW + timedelta(days=1)).isoformat(),
            "end": (FIXED_NOW + timedelta(days=1, minutes=30)).isoformat(),
        },
    )
    assert response.status_code == 401


def test_malformed_token_rejected(client):
    response = client.get(
        "/bookings/whatever", headers=auth_headers("not-a-real-token")
    )
    assert response.status_code == 401


def test_token_for_deleted_or_unknown_user_rejected(client):
    _, token = register_and_login(client, "patient", username="temp-pat")
    # Simulate the user no longer existing by clearing the store (in-memory,
    # nothing survives a reset) while keeping the previously issued token.
    from app import store

    store.reset()
    response = client.get("/bookings/whatever", headers=auth_headers(token))
    assert response.status_code == 401


@pytest.mark.usefixtures("client")
def test_expired_token_rejected(client, clock):
    _, token = register_and_login(client, "patient", username="pat-exp")
    clock.advance(timedelta(minutes=61))
    response = client.get("/bookings/whatever", headers=auth_headers(token))
    assert response.status_code == 401


# --- 5.2 require_role ---


def test_patient_forbidden_from_slot_creation(client):
    _, token = register_and_login(client, "patient")
    response = client.post(
        "/slots",
        json={
            "start": (FIXED_NOW + timedelta(days=1)).isoformat(),
            "end": (FIXED_NOW + timedelta(days=1, minutes=30)).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 403


def test_clinician_allowed_through_role_check(client):
    slot = make_slot(client, FIXED_NOW + timedelta(days=1))
    assert slot["booked"] is False
