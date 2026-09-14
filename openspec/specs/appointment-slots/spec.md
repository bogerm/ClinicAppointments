## Purpose

Lets clinicians publish bookable time slots and lets clients list slots filtered by clinician, UTC day, and availability, with consistent UTC datetime handling.

## Requirements

### Requirement: Timezone-aware datetimes normalized to UTC
The API SHALL accept datetimes only as ISO 8601 strings that include a UTC offset (`Z` or `±HH:MM`). Datetimes without an offset MUST be rejected with 422. Accepted datetimes SHALL be converted to UTC for storage, and every datetime in a response MUST be expressed in UTC with an explicit UTC designator.

#### Scenario: Offset datetime is normalized to UTC
- **WHEN** a client creates a slot with `start` `2030-01-01T11:00:00+02:00` and `end` `2030-01-01T11:30:00+02:00`
- **THEN** the response has status 201 and `start`/`end` represent `2030-01-01T09:00:00` and `2030-01-01T09:30:00` in UTC

#### Scenario: Naive datetime is rejected
- **WHEN** a client creates a slot with `start` `2030-01-01T09:00:00` (no offset)
- **THEN** the response has status 422 and no slot is created

### Requirement: Create a slot
The system SHALL provide `POST /slots` accepting a JSON body with `clinician_id` (string), `start`, and `end`. On success it MUST respond 201 with `{id, clinician_id, start, end, booked}` where `booked` is `false` and `id` is a unique, server-generated string.

#### Scenario: Valid slot created
- **WHEN** a client posts `clinician_id` `"dr-1"`, a future `start`, and an `end` 30 minutes later
- **THEN** the response has status 201 and body `{id, clinician_id: "dr-1", start, end, booked: false}`

#### Scenario: Missing field
- **WHEN** a client posts a body without `clinician_id`
- **THEN** the response has status 422

### Requirement: Slot duration and ordering validation
A slot's `end` MUST be after its `start`, and its duration MUST be between 15 and 120 minutes inclusive. Otherwise the system SHALL respond 422 and not create the slot.

#### Scenario: End before or equal to start
- **WHEN** a client posts a slot whose `end` equals or precedes `start`
- **THEN** the response has status 422

#### Scenario: Too short
- **WHEN** a client posts a slot of 14 minutes
- **THEN** the response has status 422

#### Scenario: Too long
- **WHEN** a client posts a slot of 121 minutes
- **THEN** the response has status 422

#### Scenario: Boundary durations accepted
- **WHEN** a client posts a slot of exactly 15 minutes, and another non-overlapping slot of exactly 120 minutes
- **THEN** both responses have status 201

### Requirement: Slot must not start in the past
The system SHALL reject a slot whose `start` is earlier than the current time with 422.

#### Scenario: Past start rejected
- **WHEN** a client posts a slot whose `start` is one minute before now
- **THEN** the response has status 422

### Requirement: No overlapping slots per clinician
Slots SHALL be treated as half-open intervals `[start, end)`. The system MUST reject a new slot that overlaps an existing slot of the same clinician with 409, and the error response MUST include the id of the conflicting slot. Slots of different clinicians MAY overlap. Input validation failures (422) SHALL take precedence over overlap conflicts (409).

#### Scenario: Overlap for the same clinician
- **WHEN** clinician `dr-1` has slot A `09:00–09:30` and a client posts `09:15–09:45` for `dr-1`
- **THEN** the response has status 409 and the response body contains slot A's id

#### Scenario: Adjacent slots do not overlap
- **WHEN** clinician `dr-1` has slot `09:00–09:30` and a client posts `09:30–10:00` for `dr-1`
- **THEN** the response has status 201

#### Scenario: Containing slot overlaps
- **WHEN** clinician `dr-1` has slot `09:15–09:30` and a client posts `09:00–10:00` for `dr-1`
- **THEN** the response has status 409

#### Scenario: Different clinicians may overlap
- **WHEN** clinician `dr-1` has slot `09:00–09:30` and a client posts `09:00–09:30` for `dr-2`
- **THEN** the response has status 201

#### Scenario: Offsets are compared in UTC
- **WHEN** clinician `dr-1` has slot `09:00Z–09:30Z` and a client posts `11:00+02:00–11:30+02:00` for `dr-1`
- **THEN** the response has status 409

### Requirement: List slots
The system SHALL provide `GET /slots` returning a plain JSON array of slot objects sorted by `start` ascending. It MUST support optional, combinable query parameters: `clinician_id` (exact match), `date` (`YYYY-MM-DD`, matching slots whose `start` falls on that UTC calendar day), and `available` (`true` returns only unbooked slots, `false` only booked slots). Invalid `date` or `available` values MUST yield 422.

#### Scenario: Unfiltered list sorted by start
- **WHEN** slots exist starting at 10:00, 08:00, and 09:00 and a client calls `GET /slots`
- **THEN** the response has status 200 and is a JSON array ordered 08:00, 09:00, 10:00

#### Scenario: Empty list
- **WHEN** no slots exist and a client calls `GET /slots`
- **THEN** the response has status 200 and body `[]`

#### Scenario: Filter by clinician
- **WHEN** slots exist for `dr-1` and `dr-2` and a client calls `GET /slots?clinician_id=dr-1`
- **THEN** only `dr-1` slots are returned

#### Scenario: Filter by UTC date
- **WHEN** a slot starts at `2030-01-02T01:00:00+03:00` (i.e. `2030-01-01T22:00Z`) and a client calls `GET /slots?date=2030-01-01`
- **THEN** that slot is included, and it is not included for `date=2030-01-02`

#### Scenario: Filter by availability
- **WHEN** one slot is booked and another is not
- **THEN** `GET /slots?available=true` returns only the unbooked slot and `GET /slots?available=false` returns only the booked slot

#### Scenario: Invalid date filter
- **WHEN** a client calls `GET /slots?date=01-01-2030`
- **THEN** the response has status 422
