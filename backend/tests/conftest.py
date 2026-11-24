import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_saop.db")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "-T0G16OIKi5-5C5Xju-VNBaQyQHhY1s1GOlOJ-aX3FM=")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60")
os.environ.setdefault("STAFF_JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "240")
os.environ.setdefault("MAX_FAILED_LOGIN_ATTEMPTS", "5")
os.environ.setdefault("ACCOUNT_LOCKOUT_MINUTES", "15")

import uuid
import pyotp
import pytest
from fastapi.testclient import TestClient

from src.database import Base, engine, SessionLocal
from src.main import app
from src.middleware import limiter
from src import models
from src.security import hash_password, encrypt_data, generate_totp_secret


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("test_saop.db")
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter.reset()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db_session():
    session = SessionLocal()
    yield session
    session.close()


def unique_email(prefix="user"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture()
def passenger_account(db_session):
    email = unique_email("passenger")
    password = "SecureP@ssw0rd1!"
    user = models.User(email=email, hashed_password=hash_password(password), role="passenger", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    passenger = models.Passenger(
        user_id=user.id,
        full_name=encrypt_data("Test Passenger"),
        passport_number=encrypt_data("Z9988776"),
        address=encrypt_data("1 Test Street"),
    )
    db_session.add(passenger)
    db_session.commit()
    return {"email": email, "password": password, "user": user, "passenger": passenger}


def _make_staff(db_session, role, prefix):
    email = unique_email(prefix)
    password = "StaffP@ssw0rd1!"
    secret = generate_totp_secret()
    user = models.User(email=email, hashed_password=hash_password(password), role=role, is_active=True, totp_secret=secret)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(models.Staff(user_id=user.id, full_name=f"{prefix.title()} Person", department="Ops", employee_id=uuid.uuid4().hex[:8]))
    db_session.commit()
    return {"email": email, "password": password, "user": user, "totp_secret": secret}


@pytest.fixture()
def agent_account(db_session):
    return _make_staff(db_session, "agent", "agent")


@pytest.fixture()
def crew_account(db_session):
    return _make_staff(db_session, "crew", "crew")


@pytest.fixture()
def security_account(db_session):
    return _make_staff(db_session, "security", "security")


@pytest.fixture()
def admin_account(db_session):
    return _make_staff(db_session, "admin", "admin")


@pytest.fixture()
def sample_flight(db_session):
    from datetime import datetime, timedelta
    flight = models.Flight(
        flight_number=f"TST{uuid.uuid4().hex[:5].upper()}",
        departure_time=datetime.utcnow() + timedelta(hours=2),
        arrival_time=datetime.utcnow() + timedelta(hours=5),
        from_airport="YVR",
        to_airport="YYZ",
        aircraft_id="A320",
        gate="C1",
        base_price=199.99,
        status="scheduled",
    )
    db_session.add(flight)
    db_session.commit()
    db_session.refresh(flight)
    return flight


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def login_staff_with_2fa(client, email, password, totp_secret):
    resp = login(client, email, password)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["requires_2fa"] is True
    code = pyotp.TOTP(totp_secret).now()
    resp2 = client.post("/api/v1/auth/2fa-verify", json={"user_id": body["user_id"], "totp_code": code})
    return resp2


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}
