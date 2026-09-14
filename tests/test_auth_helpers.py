from datetime import timedelta

import jwt
import pytest

from app import (
    AuthError,
    User,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from tests.conftest import FIXED_NOW


def test_password_round_trips_and_rejects_wrong_password():
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong password", hashed)


def test_decode_valid_token(auth_env):
    user = User(id="u1", username="dr-1", role="clinician", password_hash="h")
    token = create_access_token(user, FIXED_NOW)
    user_id, role = decode_access_token(token, FIXED_NOW)
    assert user_id == "u1"
    assert role == "clinician"


def test_decode_tampered_signature_rejected(auth_env):
    user = User(id="u1", username="dr-1", role="clinician", password_hash="h")
    token = create_access_token(user, FIXED_NOW)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(AuthError):
        decode_access_token(tampered, FIXED_NOW)


def test_decode_garbage_token_rejected(auth_env):
    with pytest.raises(AuthError):
        decode_access_token("not-a-jwt", FIXED_NOW)


def test_decode_expired_token_rejected(auth_env):
    user = User(id="u1", username="dr-1", role="clinician", password_hash="h")
    token = create_access_token(user, FIXED_NOW)
    later = FIXED_NOW + timedelta(minutes=61)
    with pytest.raises(AuthError):
        decode_access_token(token, later)


def test_decode_not_yet_expired_at_exact_boundary_still_valid(auth_env):
    user = User(id="u1", username="dr-1", role="clinician", password_hash="h")
    token = create_access_token(user, FIXED_NOW)
    almost_expired = FIXED_NOW + timedelta(minutes=59, seconds=59)
    user_id, _role = decode_access_token(token, almost_expired)
    assert user_id == "u1"


def test_token_signed_with_wrong_secret_rejected(auth_env):
    other_secret_token = jwt.encode(
        {"sub": "u1", "role": "clinician", "exp": FIXED_NOW.timestamp() + 3600},
        "a-different-secret",
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        decode_access_token(other_secret_token, FIXED_NOW)
