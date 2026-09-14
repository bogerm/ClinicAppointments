"""Clinic Appointment Booking API.

Clinicians publish time slots, patients book them. Storage is in-memory.
All datetimes are accepted only with an explicit offset and are stored and
returned in UTC.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field

MIN_SLOT_DURATION = timedelta(minutes=15)
MAX_SLOT_DURATION = timedelta(minutes=120)
CANCELLATION_NOTICE = timedelta(hours=24)


# --- Models -----------------------------------------------------------------


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UTCDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class SlotCreate(BaseModel):
    clinician_id: str
    start: UTCDatetime
    end: UTCDatetime


class Slot(BaseModel):
    id: str
    clinician_id: str
    start: UTCDatetime
    end: UTCDatetime
    booked: bool = False


class BookingCreate(BaseModel):
    slot_id: str
    patient_name: str = Field(min_length=1, max_length=100)


class Booking(BaseModel):
    id: str
    slot_id: str
    patient_name: str
    status: Literal["confirmed", "cancelled"] = "confirmed"
    created_at: UTCDatetime


# --- Storage ----------------------------------------------------------------


class Store:
    """In-memory store. Every read-check-write sequence must hold `lock`."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.slots: dict[str, Slot] = {}
        self.bookings: dict[str, Booking] = {}

    def reset(self) -> None:
        with self.lock:
            self.slots.clear()
            self.bookings.clear()


def new_id() -> str:
    return uuid.uuid4().hex


store = Store()


def get_store() -> Store:
    return store


def get_now() -> datetime:
    return datetime.now(UTC)


StoreDep = Annotated[Store, Depends(get_store)]
NowDep = Annotated[datetime, Depends(get_now)]


# --- Errors -----------------------------------------------------------------


class SlotConflictError(Exception):
    def __init__(self, conflicting_slot_id: str) -> None:
        self.conflicting_slot_id = conflicting_slot_id


app = FastAPI(title="Clinic Appointment Booking API")


@app.exception_handler(SlotConflictError)
def handle_slot_conflict(request: Request, exc: SlotConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": f"Slot overlaps existing slot {exc.conflicting_slot_id}",
            "conflicting_slot_id": exc.conflicting_slot_id,
        },
    )


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


# --- Slots ------------------------------------------------------------------


@app.post("/slots", status_code=status.HTTP_201_CREATED)
def create_slot(body: SlotCreate, store: StoreDep, now: NowDep) -> Slot:
    if body.end <= body.start:
        raise unprocessable("end must be after start")
    duration = body.end - body.start
    if not MIN_SLOT_DURATION <= duration <= MAX_SLOT_DURATION:
        raise unprocessable("slot duration must be between 15 and 120 minutes")
    if body.start < now:
        raise unprocessable("slot must not start in the past")

    with store.lock:
        conflicts = [
            slot
            for slot in store.slots.values()
            if slot.clinician_id == body.clinician_id
            and body.start < slot.end
            and slot.start < body.end
        ]
        if conflicts:
            earliest = min(conflicts, key=lambda s: (s.start, s.id))
            raise SlotConflictError(earliest.id)
        slot = Slot(
            id=new_id(), clinician_id=body.clinician_id, start=body.start, end=body.end
        )
        store.slots[slot.id] = slot
        return slot


@app.get("/slots")
def list_slots(
    store: StoreDep,
    clinician_id: Annotated[str | None, Query()] = None,
    date: Annotated[Date | None, Query(description="UTC day, YYYY-MM-DD")] = None,
    available: Annotated[bool | None, Query()] = None,
) -> list[Slot]:
    with store.lock:
        slots = list(store.slots.values())
    if clinician_id is not None:
        slots = [s for s in slots if s.clinician_id == clinician_id]
    if date is not None:
        slots = [s for s in slots if s.start.date() == date]
    if available is not None:
        slots = [s for s in slots if s.booked is not available]
    return sorted(slots, key=lambda s: (s.start, s.id))


# --- Bookings ---------------------------------------------------------------


@app.post("/bookings", status_code=status.HTTP_201_CREATED)
def create_booking(body: BookingCreate, store: StoreDep, now: NowDep) -> Booking:
    with store.lock:
        slot = store.slots.get(body.slot_id)
        if slot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "slot not found")
        if slot.booked:
            raise HTTPException(status.HTTP_409_CONFLICT, "slot is already booked")
        if slot.start <= now:
            raise HTTPException(status.HTTP_409_CONFLICT, "slot has already started")
        booking = Booking(
            id=new_id(),
            slot_id=slot.id,
            patient_name=body.patient_name,
            created_at=now,
        )
        store.bookings[booking.id] = booking
        slot.booked = True
        return booking


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str, store: StoreDep) -> Booking:
    booking = store.bookings.get(booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "booking not found")
    return booking


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str, store: StoreDep, now: NowDep) -> Booking:
    with store.lock:
        booking = store.bookings.get(booking_id)
        if booking is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "booking not found")
        if booking.status == "cancelled":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "booking is already cancelled"
            )
        slot = store.slots[booking.slot_id]
        if slot.start - now < CANCELLATION_NOTICE:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "bookings cannot be cancelled less than 24 hours before the slot starts",
            )
        booking.status = "cancelled"
        slot.booked = False
        return booking
