from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app import BookingCreate, RegisterRequest, SlotCreate, TokenOut, UserOut


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        SlotCreate(
            clinician_id="dr-1",
            start="2030-01-01T09:00:00",
            end="2030-01-01T09:30:00+00:00",
        )


def test_offset_normalized_to_utc():
    slot = SlotCreate(
        clinician_id="dr-1",
        start="2030-01-01T11:00:00+02:00",
        end="2030-01-01T11:30:00+02:00",
    )
    assert slot.start == datetime(2030, 1, 1, 9, 0, tzinfo=UTC)
    offset = slot.start.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0
    assert slot.model_dump(mode="json")["start"] in (
        "2030-01-01T09:00:00Z",
        "2030-01-01T09:00:00+00:00",
    )


def test_booking_create_defaults_patient_id_to_none():
    assert BookingCreate(slot_id="s").patient_id is None


def test_booking_create_accepts_explicit_patient_id():
    assert BookingCreate(slot_id="s", patient_id="pat-1").patient_id == "pat-1"


@pytest.mark.parametrize("password", ["password1", "x" * 100])
def test_register_request_password_boundaries_accepted(password):
    req = RegisterRequest(username="dr-1", password=password, role="clinician")
    assert req.password == password


def test_register_request_password_too_short_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest(username="dr-1", password="short12", role="clinician")


@pytest.mark.parametrize("role", ["admin", "wizard"])
def test_register_request_rejects_non_self_service_role(role):
    # model_validate (not the constructor) so an intentionally-bad literal
    # value can be exercised without fighting the static Literal type.
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {"username": "dr-1", "password": "password1", "role": role}
        )


@pytest.mark.parametrize("username", ["ab", "x" * 51])
def test_register_request_username_length_bounds_rejected(username):
    with pytest.raises(ValidationError):
        RegisterRequest(username=username, password="password1", role="clinician")


def test_user_out_and_token_out_never_include_password_or_hash():
    user_out = UserOut(id="u1", username="dr-1", role="clinician")
    assert "password" not in user_out.model_dump()
    assert "password_hash" not in user_out.model_dump()

    token_out = TokenOut(access_token="abc.def.ghi")
    assert token_out.model_dump() == {
        "access_token": "abc.def.ghi",
        "token_type": "bearer",
    }
