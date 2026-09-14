# Task: Clinic Appointment Booking API
## The brief

Clinicians publish time slots, patients book them. In-memory storage.
FastAPI app named `app` in `app.py`. All datetimes ISO 8601 **with an
offset**; store and return UTC.

### `POST /slots`
Body: `clinician_id` (string), `start`, `end`.
- `end` after `start`, duration between **15 and 120 minutes**, else **422**.
- Datetime without an offset: **422**.
- Slots for the **same clinician** must not overlap. Intervals are half-open,
  `[start, end)`, so 09:00-09:30 and 09:30-10:00 **do not** overlap.
  Overlap: **409**, naming the conflicting slot id.
- Slot starting in the past: **422**.

Returns **201**: `{id, clinician_id, start, end, booked: false}`.

### `GET /slots`
Query: `clinician_id`, `date` (`YYYY-MM-DD`, UTC day), `available`
(`true`/`false`). Sorted by `start` ascending. Returns a plain list.

### `POST /bookings`
Body: `slot_id`, `patient_name` (1-100 chars).
- Unknown slot: **404**.
- Slot already booked: **409**.
- Slot already started: **409**.

Returns **201**: `{id, slot_id, patient_name, status: "confirmed", created_at}`.
The slot now shows `booked: true`.

### `GET /bookings/{id}`
**200** or **404**.

### `POST /bookings/{id}/cancel`
- Sets status `cancelled`, frees the slot (`booked: false`).
- **Less than 24 hours before slot start: 409.** Exactly 24h is allowed.
- Already cancelled: **409**.