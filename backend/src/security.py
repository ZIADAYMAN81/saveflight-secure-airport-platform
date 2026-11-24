import os
import base64
import hashlib
import secrets as _secrets
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from passlib.context import CryptContext
from jose import JWTError, jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature
import pyotp

load_dotenv()

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "secret-key-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
STAFF_JWT_EXPIRES_MINUTES = int(os.getenv("STAFF_JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "240"))
DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY")

MAX_FAILED_LOGIN_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
ACCOUNT_LOCKOUT_MINUTES = int(os.getenv("ACCOUNT_LOCKOUT_MINUTES", "15"))

if not DATA_ENCRYPTION_KEY:
    DATA_ENCRYPTION_KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()

# Fernet (the previous implementation) is AES-128-CBC+HMAC, not AES-256 - use
# AES-256-GCM directly so encryption actually matches the stated requirement.
_aes_key = base64.urlsafe_b64decode(DATA_ENCRYPTION_KEY.encode())
if len(_aes_key) != 32:
    raise ValueError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256)")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(password, hashed_password)
    except Exception:
        return False


def create_access_token(subject: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    expires = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=JWT_EXPIRES_MINUTES))
    payload = {
        "sub": subject,
        "role": role,
        "exp": expires,
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        raise RuntimeError("Invalid or expired token") from exc


def encrypt_data(value: str) -> str:
    """AES-256-GCM encrypt with a fresh random nonce per call (authenticated encryption)."""
    aesgcm = AESGCM(_aes_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, value.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_data(value: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(value.encode())
        nonce, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(_aes_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    except Exception as exc:
        raise RuntimeError("Failed to decrypt data") from exc


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str, issuer: str = "Save Flight") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, token: str) -> bool:
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)
    except Exception:
        return False


def mask_card_number(card_number: str) -> tuple[str, str]:
    """Return (opaque_token, last4). The full card number is never persisted."""
    digits = "".join(ch for ch in card_number if ch.isdigit())
    last4 = digits[-4:] if len(digits) >= 4 else digits
    token = "tok_" + _secrets.token_hex(16)
    return token, last4


EMAIL_OTP_EXPIRES_MINUTES = int(os.getenv("EMAIL_OTP_EXPIRES_MINUTES", "5"))


def generate_email_otp() -> str:
    """6-digit numeric one-time code, cryptographically random (not sequential/predictable)."""
    return f"{_secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    # Short-lived, low-entropy (10^6) codes don't need a slow KDF like Argon2 -
    # the 5-minute expiry plus 5-attempt lockout are the real defenses here.
    return hashlib.sha256(code.encode()).hexdigest()


def verify_otp_hash(code: str, code_hash: Optional[str]) -> bool:
    if not code_hash:
        return False
    return hashlib.sha256(code.encode()).hexdigest() == code_hash


# --- RSA digital signatures for boarding passes -----------------------------
# This is a genuine asymmetric-key mechanism, distinct from JWT's HS256 (which
# is a symmetric HMAC, not a true digital signature - see docs/SECURITY.md).
# Only the server holds the private key; the public key can be handed to
# anyone (a gate scanner, a security auditor) to *independently* verify a
# boarding pass wasn't forged or altered, without needing DB access or trust
# in whoever is presenting it. This does NOT replace the existing DB-backed
# single-use token check (staff_routes.py still verifies `used_at` there) -
# a signature proves authenticity/integrity, not "not already redeemed";
# those are different properties and both are needed.
BOARDING_PASS_PRIVATE_KEY_PEM = os.getenv("BOARDING_PASS_PRIVATE_KEY_PEM")

if BOARDING_PASS_PRIVATE_KEY_PEM:
    _boarding_pass_private_key = serialization.load_pem_private_key(
        BOARDING_PASS_PRIVATE_KEY_PEM.encode(), password=None
    )
else:
    # No key configured (local dev/tests): generate one for this process.
    # A real deployment sets BOARDING_PASS_PRIVATE_KEY_PEM so the key is
    # stable across restarts - otherwise every prior signature becomes
    # unverifiable the moment the process recycles.
    _boarding_pass_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

_boarding_pass_public_key = _boarding_pass_private_key.public_key()


def boarding_pass_payload(booking_id: int, secure_token: str, flight_id: int, seat_number: Optional[str]) -> str:
    """Canonical string the signature commits to - both signing (check-in) and
    verification (staff redemption) must build this identically."""
    return f"{booking_id}|{secure_token}|{flight_id}|{seat_number or ''}"


def sign_boarding_pass(payload: str) -> str:
    """RSA-PSS signature (SHA-256) over the boarding pass's canonical payload."""
    signature = _boarding_pass_private_key.sign(
        payload.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return base64.urlsafe_b64encode(signature).decode()


def verify_boarding_pass_signature(payload: str, signature_b64: str) -> bool:
    try:
        signature = base64.urlsafe_b64decode(signature_b64.encode())
        _boarding_pass_public_key.verify(
            signature,
            payload.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        return True
    except (InvalidSignature, ValueError):
        return False


def boarding_pass_public_key_pem() -> str:
    """PEM-encoded public key - safe to expose publicly; only the private key must stay secret."""
    return _boarding_pass_public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
