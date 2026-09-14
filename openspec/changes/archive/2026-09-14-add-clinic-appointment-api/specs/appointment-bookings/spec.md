## Purpose

Lets patients book a published slot, look up the booking, and cancel it under the clinic's 24-hour cancellation rule, keeping each slot's `booked` flag consistent.

## ADDED Requirements

### Requirement: Create a booking
The system SHALL provide `POST /bookings` accepting a JSON body with `slot_id` (string) and `patient_name` (string of 1 to 100 characters). On success it MUST respond 201 with `{id, slot_id, patient_name, status, created_at}` where `status` is `"confirmed"`, `id` is a unique server-generated string, and `created_at` is the UTC creation time. The referenced slot MUST then report `booked: true`.

#### Scenario: Successful booking
- **WHEN** a client books an unbooked future slot with `patient_name` `"Jane Doe"`
- **THEN** the response has status 201 with `status: "confirmed"`, the given `slot_id` and `patient_name`, and a UTC `created_at`
- **AND** the slot appears with `booked: true` in `GET /slots`

#### Scenario: Patient name length boundaries
- **WHEN** a client books with a `patient_name` of 1 character or of 100 characters
- **THEN** the response has status 201

#### Scenario: Invalid patient name
- **WHEN** a client books with an empty `patient_name` or one of 101 characters
- **THEN** the response has status 422 and the slot stays unbooked

### Requirement: Booking preconditions
The system SHALL respond 404 when `slot_id` does not identify an existing slot. It SHALL respond 409 when the slot is already booked by a confirmed booking, and 409 when the slot's `start` is at or before the current time. Body validation failures (422) SHALL take precedence over these checks.

#### Scenario: Unknown slot
- **WHEN** a client books `slot_id` `"does-not-exist"`
- **THEN** the response has status 404

#### Scenario: Slot already booked
- **WHEN** a slot has a confirmed booking and a client books it again
- **THEN** the response has status 409 and the original booking is unchanged

#### Scenario: Slot already started
- **WHEN** a slot's `start` time has passed and a client books it
- **THEN** the response has status 409

### Requirement: Retrieve a booking
The system SHALL provide `GET /bookings/{id}` returning 200 with the booking object (same shape as on creation, reflecting its current `status`) or 404 if no booking has that id.

#### Scenario: Existing booking
- **WHEN** a client requests the id of an existing booking
- **THEN** the response has status 200 and the booking object

#### Scenario: Unknown booking
- **WHEN** a client requests `GET /bookings/does-not-exist`
- **THEN** the response has status 404

### Requirement: Cancel a booking
The system SHALL provide `POST /bookings/{id}/cancel`. On success it MUST set the booking's `status` to `"cancelled"`, set the slot's `booked` to `false`, and respond 200 with the updated booking. It SHALL respond 404 for an unknown booking id, 409 if the booking is already cancelled, and 409 if the time remaining until the slot's `start` is less than 24 hours. Exactly 24 hours before `start` MUST be allowed. A slot freed by cancellation SHALL be bookable again.

#### Scenario: Cancel more than 24 hours ahead
- **WHEN** a confirmed booking's slot starts in 48 hours and the client cancels it
- **THEN** the response has status 200 with `status: "cancelled"`
- **AND** the slot shows `booked: false` and `GET /bookings/{id}` returns `status: "cancelled"`

#### Scenario: Cancel exactly 24 hours ahead
- **WHEN** the current time is exactly 24 hours before the slot's `start` and the client cancels
- **THEN** the response has status 200

#### Scenario: Cancel less than 24 hours ahead
- **WHEN** the slot starts in 23 hours 59 minutes and the client cancels
- **THEN** the response has status 409 and the booking stays `confirmed` with the slot still booked

#### Scenario: Already cancelled
- **WHEN** a client cancels a booking that is already `cancelled`
- **THEN** the response has status 409

#### Scenario: Unknown booking
- **WHEN** a client cancels `does-not-exist`
- **THEN** the response has status 404

#### Scenario: Rebooking a freed slot
- **WHEN** a booking is cancelled and a client books the same slot again
- **THEN** the response has status 201 with a new booking id and the slot shows `booked: true`
