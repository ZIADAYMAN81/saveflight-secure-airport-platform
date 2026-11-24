from datetime import datetime, timedelta
from .database import engine, Base, SessionLocal, run_lightweight_migrations
from .models import User, Passenger, Staff, Flight, Booking
from .security import hash_password, encrypt_data, generate_totp_secret, totp_provisioning_uri


def _create_user_if_missing(db, email, password, role):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing, False
    user = User(email=email, hashed_password=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


def initialize_database():
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    db = SessionLocal()
    try:
        # --- Passenger ---
        user, created = _create_user_if_missing(db, "passenger@example.com", "SecureP@ssw0rd!", "passenger")
        if created:
            db.add(Passenger(
                user_id=user.id,
                full_name=encrypt_data("Alice Traveler"),
                passport_number=encrypt_data("X1234567"),
                address=encrypt_data("123 Aviation Blvd"),
                date_of_birth=datetime(1990, 5, 16),
            ))
            db.commit()

        # --- Staff (check-in agent, crew, security, admin) - all require 2FA ---
        staff_seed = [
            ("agent@example.com", "AgentP@ssw0rd1!", "agent", "Check-in Agent", "Passenger Services", "EMP1001"),
            ("crew@example.com", "CrewP@ssw0rd1!", "crew", "Flight Crew", "Flight Operations", "EMP1002"),
            ("security@example.com", "SecP@ssw0rd1!", "security", "Security Officer", "Airport Security", "EMP1003"),
            ("admin@example.com", "AdminP@ssw0rd1!", "admin", "System Administrator", "IT", "EMP1000"),
        ]
        for email, password, role, full_name, department, employee_id in staff_seed:
            user, created = _create_user_if_missing(db, email, password, role)
            if created:
                secret = generate_totp_secret()
                user.totp_secret = secret
                db.add(Staff(user_id=user.id, full_name=full_name, department=department, employee_id=employee_id))
                db.commit()
                print(f"Seeded {role} account {email} - TOTP provisioning URI:")
                print(f"  {totp_provisioning_uri(secret, email)}")

        # --- Flights ---
        if not db.query(Flight).first():
            now = datetime.utcnow()
            flights = [
                Flight(flight_number="SA123", departure_time=now + timedelta(hours=3), arrival_time=now + timedelta(hours=8),
                       from_airport="YVR", to_airport="JFK", aircraft_id="A320", gate="A12", base_price=350.00, status="scheduled"),
                Flight(flight_number="SA456", departure_time=now + timedelta(hours=6), arrival_time=now + timedelta(hours=9),
                       from_airport="YVR", to_airport="LAX", aircraft_id="B737", gate="B04", base_price=210.00, status="scheduled"),
            ]
            db.add_all(flights)
            db.commit()

            passenger = db.query(Passenger).first()
            if passenger:
                db.add(Booking(passenger_id=passenger.id, flight_id=flights[0].id, seat_number="12A", status="active"))
                db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    initialize_database()
