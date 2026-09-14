## MODIFIED Requirements

### Requirement: Create a slot
The system SHALL provide `POST /slots`, requiring a valid bearer token belonging to a `clinician` or `admin` account (see `auth` capability). A `clinician` caller MUST NOT supply `clinician_id` in the body; the slot's `clinician_id` is taken from the authenticated caller's own account. An `admin` caller MAY supply `clinician_id` in the body to create a slot on behalf of that clinician; if omitted, the request is rejected with 422. The body accepts `start` and `end`. On success it MUST respond 201 with `{id, clinician_id, start, end, booked}` where `booked` is `false` and `id` is a unique, server-generated string.

#### Scenario: Valid slot created
- **WHEN** an authenticated `clinician` with account id `"dr-1"` posts a body with a future `start` and an `end` 30 minutes later (no `clinician_id` field)
- **THEN** the response has status 201 and body `{id, clinician_id: "dr-1", start, end, booked: false}`

#### Scenario: Clinician cannot set clinician_id to someone else
- **WHEN** an authenticated `clinician` with account id `"dr-1"` posts a body that includes `clinician_id: "dr-2"`
- **THEN** the created slot's `clinician_id` is `"dr-1"` (the field is ignored, not honored) or, if the API instead treats an unexpected field as invalid input, the response is 422; in either case no slot is created for `"dr-2"`

#### Scenario: Admin creates a slot on behalf of a clinician
- **WHEN** an authenticated `admin` posts a body with `clinician_id: "dr-1"`, a future `start`, and an `end` 30 minutes later
- **THEN** the response has status 201 and body `{id, clinician_id: "dr-1", start, end, booked: false}`

#### Scenario: Admin omitting clinician_id is rejected
- **WHEN** an authenticated `admin` posts a body without `clinician_id`
- **THEN** the response has status 422

#### Scenario: Admin-supplied clinician_id must reference an existing clinician
- **WHEN** an authenticated `admin` posts a body with `clinician_id` that does not identify any existing account, or that identifies an account whose role is not `clinician`
- **THEN** the response has status 422 and no slot is created

#### Scenario: Unauthenticated request rejected
- **WHEN** a request with no valid bearer token posts to `POST /slots`
- **THEN** the response has status 401 and no slot is created

#### Scenario: Patient forbidden from creating slots
- **WHEN** an authenticated `patient` posts to `POST /slots`
- **THEN** the response has status 403 and no slot is created

#### Scenario: Missing field
- **WHEN** an authenticated `clinician` posts a body without `start` or without `end`
- **THEN** the response has status 422
