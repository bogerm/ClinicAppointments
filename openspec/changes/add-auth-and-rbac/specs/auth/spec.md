## Purpose

Provides account registration, login, and role-based access control (clinician, patient, admin) so identity on every protected endpoint comes from a verified account rather than a caller-supplied field.

## ADDED Requirements

### Requirement: Account registration
The system SHALL provide `POST /auth/register` accepting a JSON body with `username` (string, 3–50 characters, unique across all accounts), `password` (string, at least 8 characters), and `role` (one of `"clinician"`, `"patient"`). On success it MUST respond 201 with `{id, username, role}` (never the password or its hash). Passwords MUST be stored only as a salted hash, never in plain text.

#### Scenario: Successful clinician registration
- **WHEN** a client posts `username` `"dr-1"`, a valid `password`, and `role` `"clinician"`
- **THEN** the response has status 201 with `{id, username: "dr-1", role: "clinician"}` and no password field

#### Scenario: Successful patient registration
- **WHEN** a client posts a unique `username`, a valid `password`, and `role` `"patient"`
- **THEN** the response has status 201 with `role: "patient"`

#### Scenario: Duplicate username rejected
- **WHEN** a client registers a `username` that already exists (any role)
- **THEN** the response has status 409 and no account is created

#### Scenario: Password too short rejected
- **WHEN** a client registers with a `password` shorter than 8 characters
- **THEN** the response has status 422 and no account is created

#### Scenario: Invalid role rejected
- **WHEN** a client registers with `role` `"admin"` or any value other than `"clinician"`/`"patient"`
- **THEN** the response has status 422 and no account is created

### Requirement: Login issues a bearer token
The system SHALL provide `POST /auth/login` accepting a JSON body with `username` and `password`. On success it MUST respond 200 with `{access_token, token_type: "bearer"}` where `access_token` is a signed JWT encoding the account's id and role. It SHALL respond 401 for an unknown username or a wrong password, without revealing which was incorrect.

#### Scenario: Successful login
- **WHEN** a client posts the correct `username` and `password` for an existing account
- **THEN** the response has status 200 with a non-empty `access_token` and `token_type: "bearer"`

#### Scenario: Wrong password rejected
- **WHEN** a client posts a valid `username` with an incorrect `password`
- **THEN** the response has status 401

#### Scenario: Unknown username rejected
- **WHEN** a client posts a `username` that does not exist
- **THEN** the response has status 401

### Requirement: Bearer token authentication
Protected endpoints SHALL require an `Authorization: Bearer <token>` header carrying a valid, non-expired token issued by `POST /auth/login` (or the seeded admin's equivalent identity). The system SHALL respond 401 when the header is missing, malformed, expired, or carries a token that fails signature verification.

#### Scenario: Missing token rejected
- **WHEN** a client calls a protected endpoint with no `Authorization` header
- **THEN** the response has status 401

#### Scenario: Malformed or invalid token rejected
- **WHEN** a client calls a protected endpoint with an `Authorization` header that is not a valid, correctly signed token issued by this system
- **THEN** the response has status 401

#### Scenario: Expired token rejected
- **WHEN** a client calls a protected endpoint with a token whose expiry has passed
- **THEN** the response has status 401

### Requirement: Role-based access control
Each protected endpoint SHALL declare which role(s) may call it. The system SHALL respond 403 when a valid, authenticated caller's role is not permitted for the endpoint, distinct from the 401 used for missing/invalid authentication.

#### Scenario: Wrong role rejected with 403, not 401
- **WHEN** an authenticated `patient` calls an endpoint restricted to `clinician` or `admin`
- **THEN** the response has status 403 (not 401)

#### Scenario: Admin permitted wherever clinician or patient is permitted
- **WHEN** an authenticated `admin` calls an endpoint restricted to `clinician` or to `patient`
- **THEN** the request is authorized (not rejected with 403 for role reasons)

### Requirement: Exactly one seeded admin account
The system SHALL create exactly one `admin` account at process startup, from configuration (environment variables) supplying its username and password. No endpoint in this capability SHALL allow a new account to be created with role `admin`, and there is no role-promotion endpoint.

#### Scenario: Seeded admin can log in
- **WHEN** the process has started with admin credentials configured, and a client posts `POST /auth/login` with those exact credentials
- **THEN** the response has status 200 with a token whose role is `admin`

#### Scenario: Self-registration cannot create an admin
- **WHEN** a client posts `POST /auth/register` with `role` `"admin"`
- **THEN** the response has status 422 and no account is created
