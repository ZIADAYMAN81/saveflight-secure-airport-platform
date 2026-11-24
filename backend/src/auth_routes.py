from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy.orm import Session
from .schemas import LoginRequest, TokenResponse, TwoFactorVerifyRequest, RegisterRequest, UserProfile
from .models import User, Passenger
from .database import get_db
from .deps import get_current_user
from .audit import log_security_event
from .security import (
    verify_password, hash_password, create_access_token, verify_totp,
    generate_totp_secret, totp_provisioning_uri, encrypt_data,
    generate_email_otp, hash_otp, verify_otp_hash, EMAIL_OTP_EXPIRES_MINUTES,
    MAX_FAILED_LOGIN_ATTEMPTS, ACCOUNT_LOCKOUT_MINUTES,
    JWT_EXPIRES_MINUTES, STAFF_JWT_EXPIRES_MINUTES,
)
from .email_service import send_email_otp, EmailDeliveryError
from .middleware import limiter
from .metrics import failed_login_attempts_total, successful_login_total

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

STAFF_ROLES = {"agent", "crew", "security", "admin"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _token_ttl(role: str) -> timedelta:
    return timedelta(minutes=STAFF_JWT_EXPIRES_MINUTES if role in STAFF_ROLES else JWT_EXPIRES_MINUTES)


@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        # Same generic response whether the email format is bad or already taken -
        # never confirm which accounts exist.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to register with the provided details")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        role="passenger",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    passenger = Passenger(
        user_id=user.id,
        full_name=encrypt_data(payload.full_name),
        passport_number=encrypt_data(payload.passport_number),
        address=encrypt_data(payload.address) if payload.address else None,
        date_of_birth=payload.date_of_birth,
    )
    db.add(passenger)
    log_security_event(db, user.id, "REGISTER", "auth/register", _client_ip(request), "SUCCESS")
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    ip = _client_ip(request)
    generic_error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        failed_login_attempts_total.inc()
        log_security_event(db, None, "LOGIN_FAILED", "auth/login", ip, "FAILED", f"unknown or inactive email")
        raise generic_error

    if user.locked_until and user.locked_until > datetime.utcnow():
        log_security_event(db, user.id, "LOGIN_BLOCKED_LOCKED", "auth/login", ip, "FAILED")
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account temporarily locked due to failed login attempts")

    if not verify_password(payload.password, user.hashed_password):
        failed_login_attempts_total.inc()
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
            log_security_event(db, user.id, "ACCOUNT_LOCKED", "auth/login", ip, "FAILED",
                                f"{user.failed_login_attempts} consecutive failed attempts")
        db.commit()
        log_security_event(db, user.id, "LOGIN_FAILED", "auth/login", ip, "FAILED", "wrong password")
        raise generic_error

    # Valid password: reset lockout counters
    user.failed_login_attempts = 0
    user.locked_until = None

    # Staff/admin must complete 2FA before a usable token is issued. Email OTP
    # is always sent and doubles as the bootstrap method for accounts that
    # haven't enrolled an authenticator app yet - otherwise a freshly created
    # staff account (via /admin/create-staff) could never log in at all: it
    # has no TOTP secret, and enrolling one requires already being logged in.
    if user.role in STAFF_ROLES:
        otp_code = generate_email_otp()
        user.email_otp_hash = hash_otp(otp_code)
        user.email_otp_expires_at = datetime.utcnow() + timedelta(minutes=EMAIL_OTP_EXPIRES_MINUTES)
        db.commit()
        try:
            send_email_otp(user.email, otp_code, EMAIL_OTP_EXPIRES_MINUTES)
        except EmailDeliveryError:
            pass  # TOTP still works even if the email fails to send

        log_security_event(db, user.id, "LOGIN_PASSWORD_OK_2FA_PENDING", "auth/login", ip, "SUCCESS")
        return TokenResponse(access_token="", token_type="bearer", requires_2fa=True, user_id=user.id)

    user.last_login = datetime.utcnow()
    db.commit()
    token = create_access_token(str(user.id), user.role, expires_delta=_token_ttl(user.role))
    successful_login_total.inc()
    log_security_event(db, user.id, "LOGIN_SUCCESS", "auth/login", ip, "SUCCESS")
    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/2fa-verify", response_model=TokenResponse)
@limiter.limit("5/minute")
def verify_2fa(payload: TwoFactorVerifyRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid 2FA request")

    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account temporarily locked")

    email_otp_valid = (
        user.email_otp_expires_at is not None
        and user.email_otp_expires_at > datetime.utcnow()
        and verify_otp_hash(payload.totp_code, user.email_otp_hash)
    )
    totp_valid = bool(user.totp_secret) and verify_totp(user.totp_secret, payload.totp_code)

    if not totp_valid and not email_otp_valid:
        failed_login_attempts_total.inc()
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
        db.commit()
        log_security_event(db, user.id, "2FA_FAILED", "auth/2fa-verify", ip, "FAILED")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")

    # One-time use: burn the email code whether it or the TOTP code was used
    user.email_otp_hash = None
    user.email_otp_expires_at = None
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token(str(user.id), user.role, expires_delta=_token_ttl(user.role))
    successful_login_total.inc()
    log_security_event(db, user.id, "2FA_SUCCESS", "auth/2fa-verify", ip, "SUCCESS")
    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/2fa-enroll")
def enroll_2fa(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate (or rotate) a TOTP secret for the current user and return a provisioning URI
    for an authenticator app. Staff can log in via emailed OTP before enrolling this."""
    secret = generate_totp_secret()
    user.totp_secret = secret
    db.commit()
    log_security_event(db, user.id, "2FA_ENROLLED", "auth/2fa-enroll", _client_ip(request), "SUCCESS")
    return {
        "secret": secret,
        "provisioning_uri": totp_provisioning_uri(secret, user.email),
    }


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # JWTs are stateless and short-lived; logout is recorded for audit purposes
    # and the client is responsible for discarding the token.
    log_security_event(db, user.id, "LOGOUT", "auth/logout", _client_ip(request), "SUCCESS")
    return {"message": "Logged out"}
