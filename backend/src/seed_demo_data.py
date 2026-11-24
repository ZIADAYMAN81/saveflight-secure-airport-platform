"""Generates realistic demo/test data for the Save Flight platform.

Everything goes through the real application code paths - Argon2 password
hashing, AES-256-GCM PII encryption, and the tamper-evident audit-log hash
chain - rather than being hand-typed fixtures, so the data is guaranteed to
match what the running app actually produces and can be exercised through
the real API (login, boarding-pass tokens, etc).

Creates:
  - 10 flights  (real airline codes/flight numbers, mixed statuses/times)
  - 25 passengers (diverse names, encrypted PII, Argon2-hashed passwords)
  - 40 bookings  (15 checkedin / 15 active / 10 cancelled)
  - 15 check-ins (BoardingPass rows for the checkedin bookings; boarding
                   passes for already-departed/landed flights are marked used)
  - audit log entries for registration, login, booking, check-in, and staff
    gate check-in actions

Run: python -m src.seed_demo_data
Writes a plaintext reference JSON (passwords/names/passports - the DB only
ever stores the hashed/encrypted forms) and an equivalent seed_demo_data.sql
next to this file, under seed_data/ (gitignored).
"""
import json
import os
import random
import secrets as _secrets
from datetime import datetime, timedelta
from pathlib import Path

from .database import engine, Base, SessionLocal, run_lightweight_migrations
from .models import User, Passenger, Flight, Booking, BoardingPass
from .security import hash_password, encrypt_data, generate_email_otp  # noqa: F401 (kept for parity with app imports)
from .audit import log_security_event

random.seed(42)  # reproducible output across runs

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "seed_data"

# --- Reference data -----------------------------------------------------

FLIGHTS = [
    # flight_number, from, to, aircraft, gate, price, status, departure_offset_hours, duration_hours
    ("MS777",  "CAI", "JFK", "B777", "A1", 1250.00, "landed",    -48, 11),
    ("EK901",  "DXB", "CAI", "A380", "B3",  650.00, "landed",    -26, 3.5),
    ("BA110",  "LHR", "JFK", "B777", "C5",  890.00, "landed",     -6, 8),
    ("LH582",  "FRA", "CAI", "A321", "D2",  520.00, "departed",   -2, 4),
    ("SV052",  "JED", "CAI", "A320", "A7",  410.00, "departed", -0.5, 2.5),
    ("QR1301", "DOH", "CAI", "A350", "B1",  580.00, "boarding",  0.75, 4),
    ("TK694",  "IST", "CAI", "B737", "C3",  390.00, "boarding",     1, 2.5),
    ("AF563",  "CDG", "CAI", "A330", "D4",  720.00, "scheduled",    5, 5),
    ("EY608",  "AUH", "CAI", "A321", "A2",  470.00, "scheduled",   26, 4),
    ("KU541",  "RUH", "CAI", "A320", "B6",  440.00, "scheduled",   50, 2.5),
]

PASSENGERS = [
    # full_name, nationality_code, city
    ("Ahmed Hassan", "EG", "Cairo"),
    ("Mona Ibrahim", "EG", "Alexandria"),
    ("Youssef El-Sayed", "EG", "Giza"),
    ("Fatma Abdelrahman", "EG", "Luxor"),
    ("Omar Khaled", "EG", "Cairo"),
    ("Nour Mahmoud", "EG", "Aswan"),
    ("Karim Adel", "EG", "Mansoura"),
    ("Salma Farouk", "EG", "Tanta"),
    ("James Anderson", "US", "New York"),
    ("Emily Clark", "GB", "London"),
    ("Michael Brown", "US", "Chicago"),
    ("Sarah Wilson", "GB", "Manchester"),
    ("David Miller", "US", "Boston"),
    ("Jessica Taylor", "CA", "Toronto"),
    ("Robert Johnson", "US", "Houston"),
    ("Laura Martinez", "ES", "Madrid"),
    ("William Davis", "AU", "Sydney"),
    ("Hiroshi Tanaka", "JP", "Tokyo"),
    ("Mei Ling Wong", "CN", "Shanghai"),
    ("Raj Patel", "IN", "Mumbai"),
    ("Yuki Sato", "JP", "Osaka"),
    ("Wei Chen", "CN", "Beijing"),
    ("Priya Sharma", "IN", "Delhi"),
    ("Kenji Yamamoto", "JP", "Kyoto"),
    ("Anjali Gupta", "IN", "Bangalore"),
]

SEAT_ROWS = list(range(1, 46))
SEAT_LETTERS = ["A", "B", "C", "D", "E", "F"]


def _email_for(full_name: str, index: int) -> str:
    parts = full_name.lower().replace("-", " ").split()
    return f"{parts[0]}.{parts[-1]}{index}@example.com"


def _password_for(full_name: str, index: int) -> str:
    first = full_name.split()[0]
    return f"{first}{index}@2026!"


def _passport_for(nationality: str, index: int) -> str:
    return f"{nationality}{100000 + index * 37}"[:9]


def _pick_seat(taken: set) -> str:
    while True:
        seat = f"{random.choice(SEAT_ROWS)}{random.choice(SEAT_LETTERS)}"
        if seat not in taken:
            taken.add(seat)
            return seat


def seed():
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    db = SessionLocal()
    now = datetime.utcnow()
    reference = {"flights": [], "passengers": [], "bookings": [], "check_ins": []}
    sql_lines = []

    try:
        # --- Flights ---
        flight_rows = []
        for flight_number, frm, to, aircraft, gate, price, status, dep_offset, duration in FLIGHTS:
            existing = db.query(Flight).filter(Flight.flight_number == flight_number).first()
            if existing:
                flight_rows.append(existing)
                continue
            departure = now + timedelta(hours=dep_offset)
            arrival = departure + timedelta(hours=duration)
            flight = Flight(
                flight_number=flight_number, departure_time=departure, arrival_time=arrival,
                from_airport=frm, to_airport=to, aircraft_id=aircraft, gate=gate,
                base_price=price, status=status,
            )
            db.add(flight)
            db.flush()
            flight_rows.append(flight)
            reference["flights"].append({
                "flight_number": flight_number, "from": frm, "to": to, "aircraft": aircraft,
                "gate": gate, "price": price, "status": status,
                "departure_time": departure.isoformat(), "arrival_time": arrival.isoformat(),
            })
            sql_lines.append(
                f"INSERT INTO flights (flight_number, departure_time, arrival_time, from_airport, to_airport, "
                f"aircraft_id, gate, base_price, status) VALUES "
                f"('{flight_number}', '{departure.isoformat()}', '{arrival.isoformat()}', '{frm}', '{to}', "
                f"'{aircraft}', '{gate}', {price}, '{status}');"
            )
        db.commit()

        # --- Passengers (User + Passenger) ---
        passenger_rows = []
        passenger_email_by_id = {}
        agent = db.query(User).filter(User.email == "agent@example.com").first()

        for idx, (full_name, nationality, city) in enumerate(PASSENGERS, start=1):
            email = _email_for(full_name, idx)
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                existing_passenger = db.query(Passenger).filter(Passenger.user_id == existing_user.id).first()
                passenger_rows.append(existing_passenger)
                passenger_email_by_id[existing_passenger.id] = email
                continue

            password = _password_for(full_name, idx)
            passport = _passport_for(nationality, idx)
            dob = now - timedelta(days=random.randint(20 * 365, 60 * 365))

            user = User(email=email, hashed_password=hash_password(password), role="passenger", is_active=True,
                        created_at=now - timedelta(days=random.randint(5, 120)))
            db.add(user)
            db.flush()

            passenger = Passenger(
                user_id=user.id,
                full_name=encrypt_data(full_name),
                passport_number=encrypt_data(passport),
                address=encrypt_data(f"{random.randint(1, 200)} Airport Rd, {city}"),
                date_of_birth=dob,
            )
            db.add(passenger)
            db.flush()
            passenger_rows.append(passenger)
            passenger_email_by_id[passenger.id] = email

            log_security_event(db, user.id, "REGISTER", "auth/register", "203.0.113." + str(idx % 250), "SUCCESS")
            if random.random() < 0.8:
                log_security_event(db, user.id, "LOGIN_SUCCESS", "auth/login", "203.0.113." + str(idx % 250), "SUCCESS")

            reference["passengers"].append({
                "full_name": full_name, "email": email, "password": password,
                "passport_number": passport, "nationality": nationality, "city": city,
                "date_of_birth": dob.date().isoformat(),
            })
            sql_lines.append(
                f"-- passenger: {full_name} <{email}> (password shown is pre-hash, see seed_demo_data.json)"
            )
        db.commit()

        # --- Bookings + check-ins ---
        target_counts = {"checkedin": 15, "active": 15, "cancelled": 10}
        statuses = (["checkedin"] * target_counts["checkedin"]
                    + ["active"] * target_counts["active"]
                    + ["cancelled"] * target_counts["cancelled"])
        random.shuffle(statuses)

        seats_per_flight = {f.id: set() for f in flight_rows}
        checkin_count = 0

        for i, status in enumerate(statuses):
            passenger = passenger_rows[i % len(passenger_rows)]
            flight = flight_rows[i % len(flight_rows)]
            seat = _pick_seat(seats_per_flight[flight.id])
            created_at = now - timedelta(days=random.randint(1, 30))

            booking = Booking(passenger_id=passenger.id, flight_id=flight.id, seat_number=seat,
                               status=status, created_at=created_at)
            db.add(booking)
            db.flush()

            log_security_event(db, passenger.user_id, "BOOKING_CREATED", "booking/create",
                               "198.51.100." + str(i % 250), "SUCCESS", f"flight_id={flight.id}")

            reference["bookings"].append({
                "passenger_email": passenger_email_by_id.get(passenger.id),
                "flight_number": flight.flight_number, "seat": seat, "status": status,
                "created_at": created_at.isoformat(),
            })

            if status == "checkedin":
                checkin_count += 1
                token = _secrets.token_urlsafe(32)
                boarded = flight.status in ("departed", "landed")
                boarding_pass = BoardingPass(
                    booking_id=booking.id,
                    secure_token=token,
                    used_at=(created_at + timedelta(hours=random.randint(1, 6))) if boarded else None,
                    checked_in_by=agent.id if (boarded and agent) else None,
                    created_at=created_at,
                )
                db.add(boarding_pass)
                db.flush()

                log_security_event(db, passenger.user_id, "CHECKIN_CREATED", "passenger/checkin",
                                   "198.51.100." + str(i % 250), "SUCCESS", f"booking_id={booking.id}")
                if boarded and agent:
                    log_security_event(db, agent.id, "STAFF_CHECKIN_SUCCESS", "staff/checkin-passenger",
                                        "192.0.2." + str(i % 250), "SUCCESS", f"boarding_pass_id={boarding_pass.id}")

                reference["check_ins"].append({
                    "flight_number": flight.flight_number, "seat": seat,
                    "boarding_pass_token": token, "boarded": boarded,
                })

        db.commit()

    finally:
        db.close()

    # All DB writes are already committed at this point - this is just a
    # human-readable reference dump, and containers may run with a read-only
    # root filesystem (see docker-compose.yml's `read_only: true` on
    # backend). Fall back to /tmp rather than letting a cosmetic file-write
    # crash the whole seed run after the real work already succeeded.
    output_dir = OUTPUT_DIR
    try:
        output_dir.mkdir(exist_ok=True)
        with open(output_dir / "seed_demo_data.json", "w") as f:
            json.dump(reference, f, indent=2, default=str)
    except OSError:
        output_dir = Path("/tmp/seed_data")
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "seed_demo_data.json", "w") as f:
            json.dump(reference, f, indent=2, default=str)

    with open(output_dir / "seed_demo_data.sql", "w") as f:
        f.write("-- Reference SQL for the flights created by seed_demo_data.py\n")
        f.write("-- Passengers/bookings/check-ins involve hashed passwords and AES-256-GCM\n")
        f.write("-- encrypted PII whose ciphertext is tied to this deployment's DATA_ENCRYPTION_KEY -\n")
        f.write("-- run `python -m src.seed_demo_data` directly instead of pasting SQL for those.\n\n")
        f.write("\n".join(sql_lines) + "\n")

    print(f"Seeded {len(reference['flights'])} new flights, {len(reference['passengers'])} new passengers, "
          f"{len(statuses)} bookings ({checkin_count} checked in).")
    print(f"Reference data written to {output_dir / 'seed_demo_data.json'}")
    print(f"Flight SQL written to {output_dir / 'seed_demo_data.sql'}")


if __name__ == "__main__":
    seed()
