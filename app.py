"""Clinic Appointment Booking API.

Clinicians publish time slots, patients book them. Storage is in-memory.
All datetimes are accepted only with an explicit offset and are stored and
returned in UTC.

Authentication is via self-issued JWT bearer tokens (see the `auth`
capability). Three roles exist: clinician, patient, admin. An admin account
is seeded at startup from ADMIN_USERNAME/ADMIN_PASSWORD; AUTH_SECRET_KEY is
required and signs/verifies tokens.
"""

import logging
import os
import threading
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Annotated, Literal

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field

logger = logging.getLogger(__name__)

MIN_SLOT_DURATION = timedelta(minutes=15)
MAX_SLOT_DURATION = timedelta(minutes=120)
CANCELLATION_NOTICE = timedelta(hours=24)

ACCESS_TOKEN_EXPIRE_MINUTES = 60
JWT_ALGORITHM = "HS256"


# --- Models -----------------------------------------------------------------


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UTCDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]

Role = Literal["clinician", "patient", "admin"]


class SlotCreate(BaseModel):
    clinician_id: str | None = None
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
    patient_id: str | None = None


class Booking(BaseModel):
    id: str
    slot_id: str
    patient_id: str
    status: Literal["confirmed", "cancelled"] = "confirmed"
    created_at: UTCDatetime


class User(BaseModel):
    id: str
    username: str
    role: Role
    password_hash: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)
    role: Literal["clinician", "patient"]


class UserOut(BaseModel):
    id: str
    username: str
    role: Role


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


# --- Storage ----------------------------------------------------------------


class Store:
    """In-memory store. Every read-check-write sequence must hold `lock`."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.slots: dict[str, Slot] = {}
        self.bookings: dict[str, Booking] = {}
        self.users: dict[str, User] = {}
        self.username_index: dict[str, str] = {}

    def reset(self) -> None:
        with self.lock:
            self.slots.clear()
            self.bookings.clear()
            self.users.clear()
            self.username_index.clear()


def new_id() -> str:
    return uuid.uuid4().hex


store = Store()


def get_store() -> Store:
    return store


def get_now() -> datetime:
    return datetime.now(UTC)


StoreDep = Annotated[Store, Depends(get_store)]
NowDep = Annotated[datetime, Depends(get_now)]


# --- Password hashing ---------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# --- JWT ----------------------------------------------------------------------


class AuthError(Exception):
    """Raised for any token that cannot be trusted (bad signature, expired, malformed)."""


def _secret_key() -> str:
    key = os.environ.get("AUTH_SECRET_KEY")
    if not key:
        raise RuntimeError("AUTH_SECRET_KEY environment variable must be set")
    return key


def create_access_token(user: User, now: datetime) -> str:
    payload = {
        "sub": user.id,
        "role": user.role,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _secret_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, now: datetime) -> tuple[str, Role]:
    """Return (user_id, role), checking expiry against `now` rather than wall-clock
    so tests can simulate an expired token via the injectable clock."""
    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("invalid token") from exc
    exp = payload.get("exp")
    if exp is None or now.timestamp() >= exp:
        raise AuthError("token expired")
    user_id = payload.get("sub")
    role = payload.get("role")
    if not isinstance(user_id, str) or role not in ("clinician", "patient", "admin"):
        raise AuthError("invalid token")
    return user_id, role


# --- Auth dependencies ---------------------------------------------------------


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    store: StoreDep,
    now: NowDep,
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id, role = decode_access_token(token, now)
    except AuthError as exc:
        raise unauthorized from exc
    user = store.users.get(user_id)
    if user is None or user.role != role:
        raise unauthorized
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role) -> Callable[[CurrentUserDep], User]:
    def dependency(current: CurrentUserDep) -> User:
        if current.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return current

    return dependency


# --- Errors -----------------------------------------------------------------


class SlotConflictError(Exception):
    def __init__(self, conflicting_slot_id: str) -> None:
        self.conflicting_slot_id = conflicting_slot_id


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


# --- App / startup -------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _secret_key()  # fail fast if unset; no insecure default
    admin_username = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_username and admin_password:
        with store.lock:
            if admin_username not in store.username_index:
                admin = User(
                    id=new_id(),
                    username=admin_username,
                    role="admin",
                    password_hash=hash_password(admin_password),
                )
                store.users[admin.id] = admin
                store.username_index[admin.username] = admin.id
    else:
        logger.warning("ADMIN_USERNAME/ADMIN_PASSWORD not set; no admin account seeded")
    yield


app = FastAPI(title="Clinic Appointment Booking API", lifespan=lifespan)


@app.exception_handler(SlotConflictError)
def handle_slot_conflict(request: Request, exc: SlotConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": f"Slot overlaps existing slot {exc.conflicting_slot_id}",
            "conflicting_slot_id": exc.conflicting_slot_id,
        },
    )


# --- Auth ---------------------------------------------------------------------


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, store: StoreDep) -> UserOut:
    with store.lock:
        if body.username in store.username_index:
            raise HTTPException(status.HTTP_409_CONFLICT, "username already registered")
        user = User(
            id=new_id(),
            username=body.username,
            role=body.role,
            password_hash=hash_password(body.password),
        )
        store.users[user.id] = user
        store.username_index[user.username] = user.id
        return UserOut(id=user.id, username=user.username, role=user.role)


@app.post("/auth/login")
def login(body: LoginRequest, store: StoreDep, now: NowDep) -> TokenOut:
    with store.lock:
        user_id = store.username_index.get(body.username)
        user = store.users.get(user_id) if user_id else None
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "incorrect username or password"
        )
    return TokenOut(access_token=create_access_token(user, now))


# --- Slots ------------------------------------------------------------------


@app.post("/slots", status_code=status.HTTP_201_CREATED)
def create_slot(
    body: SlotCreate,
    store: StoreDep,
    now: NowDep,
    current: Annotated[User, Depends(require_role("clinician", "admin"))],
) -> Slot:
    if body.end <= body.start:
        raise unprocessable("end must be after start")
    duration = body.end - body.start
    if not MIN_SLOT_DURATION <= duration <= MAX_SLOT_DURATION:
        raise unprocessable("slot duration must be between 15 and 120 minutes")
    if body.start < now:
        raise unprocessable("slot must not start in the past")

    with store.lock:
        if current.role == "clinician":
            clinician_id = current.id
        else:
            if body.clinician_id is None:
                raise unprocessable("clinician_id is required for admin-created slots")
            clinician = store.users.get(body.clinician_id)
            if clinician is None or clinician.role != "clinician":
                raise unprocessable(
                    "clinician_id must reference an existing clinician account"
                )
            clinician_id = body.clinician_id

        conflicts = [
            slot
            for slot in store.slots.values()
            if slot.clinician_id == clinician_id
            and body.start < slot.end
            and slot.start < body.end
        ]
        if conflicts:
            earliest = min(conflicts, key=lambda s: (s.start, s.id))
            raise SlotConflictError(earliest.id)
        slot = Slot(
            id=new_id(), clinician_id=clinician_id, start=body.start, end=body.end
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
def create_booking(
    body: BookingCreate,
    store: StoreDep,
    now: NowDep,
    current: Annotated[User, Depends(require_role("patient", "admin"))],
) -> Booking:
    with store.lock:
        if current.role == "patient":
            patient_id = current.id
        else:
            if body.patient_id is None:
                raise unprocessable("patient_id is required for admin-created bookings")
            patient = store.users.get(body.patient_id)
            if patient is None or patient.role != "patient":
                raise unprocessable(
                    "patient_id must reference an existing patient account"
                )
            patient_id = body.patient_id

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
            patient_id=patient_id,
            created_at=now,
        )
        store.bookings[booking.id] = booking
        slot.booked = True
        return booking


@app.get("/bookings/{booking_id}")
def get_booking(
    booking_id: str,
    store: StoreDep,
    current: CurrentUserDep,
) -> Booking:
    booking = store.bookings.get(booking_id)
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "booking not found")
    if current.role != "admin" and booking.patient_id != current.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "not allowed to view this booking"
        )
    return booking


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: str,
    store: StoreDep,
    now: NowDep,
    current: CurrentUserDep,
) -> Booking:
    with store.lock:
        booking = store.bookings.get(booking_id)
        if booking is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "booking not found")
        if current.role != "admin" and booking.patient_id != current.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "not allowed to cancel this booking"
            )
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
