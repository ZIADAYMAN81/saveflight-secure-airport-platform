"""Explicit, individually-named tests for security properties that were
already exercised indirectly elsewhere but didn't have a dedicated test:
crypto round-trip integrity, JWT expiry enforcement, and ORM-level SQL
injection resistance.
"""
from datetime import timedelta

from src.security import (
    encrypt_data, decrypt_data, create_access_token, decode_access_token,
    sign_boarding_pass, verify_boarding_pass_signature, boarding_pass_payload,
)
from src import models
from .conftest import login, login_staff_with_2fa, auth_headers


def test_encryption_roundtrip():
    plaintext = "A1234567 - Ahmed Hassan, 12 Nile St, Cairo"
    ciphertext = encrypt_data(plaintext)

    assert ciphertext != plaintext
    assert decrypt_data(ciphertext) == plaintext

    # GCM is authenticated: flipping a single character in the stored blob
    # must break decryption rather than silently returning altered plaintext.
    tampered = ("X" if ciphertext[0] != "X" else "Y") + ciphertext[1:]
    try:
        decrypt_data(tampered)
        assert False, "decrypt_data should reject a tampered ciphertext"
    except RuntimeError:
        pass


def test_jwt_token_expiration():
    # A token minted with a negative TTL is already expired the instant it's created.
    expired_token = create_access_token("123", "passenger", expires_delta=timedelta(minutes=-5))
    try:
        decode_access_token(expired_token)
        assert False, "decode_access_token should reject an expired token"
    except RuntimeError:
        pass

    # A freshly-issued token with a normal TTL must still decode successfully.
    valid_token = create_access_token("123", "passenger", expires_delta=timedelta(minutes=60))
    payload = decode_access_token(valid_token)
    assert payload["sub"] == "123"
    assert payload["role"] == "passenger"


def test_expired_token_rejected_by_protected_endpoint(client, passenger_account):
    expired_token = create_access_token(str(passenger_account["user"].id), "passenger", expires_delta=timedelta(minutes=-1))
    resp = client.get("/api/v1/passenger/bookings", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


def test_sql_injection_prevention(client, db_session):
    # Classic tautology/DROP-style payloads submitted through the public login
    # endpoint. Two independent layers stop these: Pydantic's EmailStr schema
    # rejects anything that isn't email-shaped (422) before the DB is ever
    # touched, and for payloads that happen to look like an email,
    # SQLAlchemy's ORM sends the value as a bound parameter - so it can only
    # ever match a literal (nonexistent) string, never alter the query
    # structure or execute a second statement.
    payloads = [
        "' OR '1'='1",
        "' OR '1'='1' -- ",
        "'; DROP TABLE users; --",
        "admin@example.com' --",
    ]
    for payload in payloads:
        resp = client.post("/api/v1/auth/login", json={"email": payload, "password": "irrelevant"})
        assert resp.status_code in (401, 422), f"payload {payload!r} must be rejected, not executed: got {resp.status_code}"

    # The users table must still exist and be intact - a successful injection
    # of "DROP TABLE users" would make this raise instead of returning a count.
    assert db_session.query(models.User).count() >= 0


def test_boarding_pass_rsa_signature_roundtrip():
    payload = boarding_pass_payload(42, "some-secure-token", 7, "12A")
    signature = sign_boarding_pass(payload)

    assert verify_boarding_pass_signature(payload, signature) is True
    # Any change to the signed content - even a different seat number - must
    # invalidate the signature, since it's computed over the exact payload.
    tampered_payload = boarding_pass_payload(42, "some-secure-token", 7, "99Z")
    assert verify_boarding_pass_signature(tampered_payload, signature) is False


def test_boarding_pass_signature_present_and_valid_end_to_end(client, passenger_account, sample_flight):
    pax_token = login(client, passenger_account["email"], passenger_account["password"]).json()["access_token"]
    booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token)).json()
    checkin = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=auth_headers(pax_token)).json()

    assert checkin["signature"]
    payload = boarding_pass_payload(booking["id"], checkin["boarding_pass_token"], booking["flight_id"], booking.get("seat_number"))
    assert verify_boarding_pass_signature(payload, checkin["signature"]) is True


def test_tampered_boarding_pass_fails_staff_redemption(client, db_session, agent_account, passenger_account, sample_flight):
    pax_token = login(client, passenger_account["email"], passenger_account["password"]).json()["access_token"]
    booking = client.post("/api/v1/booking/create", json={"flight_id": sample_flight.id}, headers=auth_headers(pax_token)).json()
    checkin = client.post("/api/v1/passenger/checkin", json={"booking_id": booking["id"]}, headers=auth_headers(pax_token)).json()

    # Simulate a direct-DB tamper (e.g. compromised credentials, bypassing the
    # app entirely) that reassigns the boarding pass to a different flight -
    # the token itself still matches, but the signature no longer commits to
    # this row's current content.
    bp = db_session.query(models.BoardingPass).filter(models.BoardingPass.secure_token == checkin["boarding_pass_token"]).first()
    tampered_booking = db_session.query(models.Booking).filter(models.Booking.id == bp.booking_id).first()
    tampered_booking.flight_id = tampered_booking.flight_id + 1
    db_session.commit()

    agent_token = login_staff_with_2fa(client, agent_account["email"], agent_account["password"], agent_account["totp_secret"]).json()["access_token"]
    resp = client.post("/api/v1/staff/checkin-passenger", json={"boarding_pass_token": checkin["boarding_pass_token"]}, headers=auth_headers(agent_token))
    assert resp.status_code == 409


def test_boarding_pass_public_key_endpoint_is_unauthenticated(client):
    resp = client.get("/api/v1/boarding-pass/public-key")
    assert resp.status_code == 200
    body = resp.json()
    assert "BEGIN PUBLIC KEY" in body["public_key_pem"]
    assert body["algorithm"].startswith("RSA")
