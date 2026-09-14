## MODIFIED Requirements

### Requirement: Create a booking
The system SHALL provide `POST /bookings`, requiring a valid bearer token belonging to a `patient` or `admin` account (see `auth` capability). A `patient` caller MUST NOT supply `patient_name`/patient identity in the body; the booking's patient is taken from the authenticated caller's own account. An `admin` caller MAY supply a `patient_id` in the body to book on behalf of that patient; if omitted, the request is rejected with 422. The body accepts `slot_id`. On success it MUST respond 201 with `{id, slot_id, patient_id, status, created_at}` where `status` is `"confirmed"`, `id` is a unique server-generated string, and `created_at` is the UTC creation time. The referenced slot MUST then report `booked: true`.

#### Scenario: Successful booking
- **WHEN** an authenticated `patient` with account id `"pat-1"` posts `{slot_id}` for an unbooked future slot
- **THEN** the response has status 201 with `status: "confirmed"`, `patient_id: "pat-1"`, the given `slot_id`, and a UTC `created_at`
- **AND** the slot appears with `booked: true` in `GET /slots`

#### Scenario: Patient name length boundaries
- **WHEN** an authenticated `admin` posts `{slot_id, patient_id}` where `patient_id` identifies an existing account whose role is not `patient` (e.g. a `clinician` account)
- **THEN** the response has status 422 and no booking is created

#### Scenario: Invalid patient name
- **WHEN** an authenticated `admin` posts `{slot_id, patient_id}` where `patient_id` does not identify any existing account
- **THEN** the response has status 422 and no booking is created

#### Scenario: Admin books on behalf of a patient
- **WHEN** an authenticated `admin` posts `{slot_id, patient_id: "pat-1"}` for an unbooked future slot
- **THEN** the response has status 201 with `patient_id: "pat-1"`

#### Scenario: Admin omitting patient_id is rejected
- **WHEN** an authenticated `admin` posts `{slot_id}` without `patient_id`
- **THEN** the response has status 422

#### Scenario: Unauthenticated request rejected
- **WHEN** a request with no valid bearer token posts to `POST /bookings`
- **THEN** the response has status 401 and no booking is created

#### Scenario: Clinician forbidden from booking
- **WHEN** an authenticated `clinician` posts to `POST /bookings`
- **THEN** the response has status 403 and no booking is created

### Requirement: Booking preconditions
The system SHALL respond 404 when `slot_id` does not identify an existing slot. It SHALL respond 409 when the slot is already booked by a confirmed booking, and 409 when the slot's `start` is at or before the current time. Body validation and authentication/authorization failures (422/401/403) SHALL take precedence over these 404/409 checks.

#### Scenario: Unknown slot
- **WHEN** an authenticated `patient` books `slot_id` `"does-not-exist"`
- **THEN** the response has status 404

#### Scenario: Slot already booked
- **WHEN** a slot has a confirmed booking and an authenticated `patient` books it again
- **THEN** the response has status 409 and the original booking is unchanged

#### Scenario: Slot already started
- **WHEN** a slot's `start` time has passed and an authenticated `patient` books it
- **THEN** the response has status 409

### Requirement: Retrieve a booking
The system SHALL provide `GET /bookings/{id}`, requiring a valid bearer token. It SHALL respond 200 with the booking object (same shape as on creation, reflecting its current `status`) when the caller is the booking's own patient or an `admin`. It SHALL respond 403 when the caller is authenticated but is neither the booking's own patient nor an `admin`, and 404 if no booking has that id. A 404 for a genuinely unknown id SHALL be returned regardless of role, so an unauthorized caller cannot distinguish "not yours" from "doesn't exist" beyond the 403/404 the spec defines here.

#### Scenario: Existing booking
- **WHEN** the patient who owns a booking requests `GET /bookings/{id}` for it
- **THEN** the response has status 200 and the booking object

#### Scenario: Admin retrieves any booking
- **WHEN** an authenticated `admin` requests `GET /bookings/{id}` for any existing booking
- **THEN** the response has status 200 and the booking object

#### Scenario: Non-owning patient forbidden
- **WHEN** a `patient` who does not own a booking requests `GET /bookings/{id}` for it
- **THEN** the response has status 403

#### Scenario: Unknown booking
- **WHEN** an authenticated caller requests `GET /bookings/does-not-exist`
- **THEN** the response has status 404

#### Scenario: Unauthenticated request rejected
- **WHEN** a request with no valid bearer token calls `GET /bookings/{id}`
- **THEN** the response has status 401

### Requirement: Cancel a booking
The system SHALL provide `POST /bookings/{id}/cancel`, requiring a valid bearer token belonging to the booking's own patient or an `admin`. On success it MUST set the booking's `status` to `"cancelled"`, set the slot's `booked` to `false`, and respond 200 with the updated booking. It SHALL respond 403 when the caller is authenticated but is neither the booking's own patient nor an `admin`, 404 for an unknown booking id, 409 if the booking is already cancelled, and 409 if the time remaining until the slot's `start` is less than 24 hours. Exactly 24 hours before `start` MUST be allowed. A slot freed by cancellation SHALL be bookable again.

#### Scenario: Cancel more than 24 hours ahead
- **WHEN** the patient who owns a confirmed booking whose slot starts in 48 hours cancels it
- **THEN** the response has status 200 with `status: "cancelled"`
- **AND** the slot shows `booked: false` and `GET /bookings/{id}` returns `status: "cancelled"`

#### Scenario: Admin cancels any booking
- **WHEN** an authenticated `admin` cancels a confirmed booking whose slot starts in 48 hours
- **THEN** the response has status 200 with `status: "cancelled"`

#### Scenario: Non-owning patient forbidden from cancelling
- **WHEN** a `patient` who does not own a booking calls `POST /bookings/{id}/cancel` for it
- **THEN** the response has status 403 and the booking is unchanged

#### Scenario: Cancel exactly 24 hours ahead
- **WHEN** the owning patient cancels at exactly 24 hours before the slot's `start`
- **THEN** the response has status 200

#### Scenario: Cancel less than 24 hours ahead
- **WHEN** the owning patient cancels when the slot starts in 23 hours 59 minutes
- **THEN** the response has status 409 and the booking stays `confirmed` with the slot still booked

#### Scenario: Already cancelled
- **WHEN** the owning patient cancels a booking that is already `cancelled`
- **THEN** the response has status 409

#### Scenario: Unknown booking
- **WHEN** an authenticated caller cancels `does-not-exist`
- **THEN** the response has status 404

#### Scenario: Unauthenticated request rejected
- **WHEN** a request with no valid bearer token calls `POST /bookings/{id}/cancel`
- **THEN** the response has status 401

#### Scenario: Rebooking a freed slot
- **WHEN** a booking is cancelled and an authenticated `patient` books the same slot again
- **THEN** the response has status 201 with a new booking id and the slot shows `booked: true`
