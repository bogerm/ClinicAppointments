from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app import BookingCreate, SlotCreate


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


@pytest.mark.parametrize("name", ["J", "x" * 100])
def test_patient_name_boundaries_accepted(name):
    assert BookingCreate(slot_id="s", patient_name=name).patient_name == name


@pytest.mark.parametrize("name", ["", "x" * 101])
def test_patient_name_out_of_bounds_rejected(name):
    with pytest.raises(ValidationError):
        BookingCreate(slot_id="s", patient_name=name)
