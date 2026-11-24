from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="passenger", nullable=False)
    # passenger, agent, crew, security, admin
    totp_secret = Column(String, nullable=True)
    email_otp_hash = Column(String, nullable=True)
    email_otp_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    passenger = relationship("Passenger", back_populates="user", uselist=False)
    staff_profile = relationship("Staff", back_populates="user", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="user")


class Passenger(Base):
    __tablename__ = "passengers"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    passport_number = Column(String, nullable=False)
    address = Column(String, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="passenger")


class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    department = Column(String, nullable=True)
    employee_id = Column(String, unique=True, nullable=False)

    user = relationship("User", back_populates="staff_profile")


class Flight(Base):
    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, index=True)
    flight_number = Column(String, unique=True, index=True, nullable=False)
    departure_time = Column(DateTime, index=True, nullable=False)
    arrival_time = Column(DateTime, nullable=False)
    from_airport = Column(String, nullable=False)
    to_airport = Column(String, nullable=False)
    aircraft_id = Column(String, nullable=True)
    gate = Column(String, nullable=True)
    terminal = Column(String, nullable=True)
    base_price = Column(Numeric(10, 2), default=0, nullable=False)
    status = Column(String, default="scheduled", nullable=False)
    # scheduled, boarding, departed, landed, cancelled


class Seat(Base):
    __tablename__ = "seats"

    id = Column(Integer, primary_key=True, index=True)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False, index=True)
    seat_number = Column(String, nullable=False)
    # e.g. "1A" .. "50F" - 6-across (3-3) layout
    seat_class = Column(String, nullable=False)
    # first (rows 1-4), business (rows 5-12), economy (rows 13-50)
    position = Column(String, nullable=False)
    # window, middle, aisle
    is_exit_row = Column(Boolean, default=False, nullable=False)
    is_restricted = Column(Boolean, default=False, nullable=False)
    # e.g. crew-reserved / structurally blocked seats, independent of booking status

    # Price is never stored here - it's always derived from the parent flight's
    # base_price x a per-class multiplier at request time, so it can't go stale
    # and a client can never influence what gets charged.


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    passenger_id = Column(Integer, ForeignKey("passengers.id"), nullable=False, index=True)
    flight_id = Column(Integer, ForeignKey("flights.id"), nullable=False)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=True)
    seat_number = Column(String, nullable=True)
    # denormalized display copy of seats.seat_number, set at booking time
    status = Column(String, default="active", nullable=False)
    # active, checkedin, cancelled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    passenger = relationship("Passenger")
    flight = relationship("Flight")
    seat = relationship("Seat")

    @property
    def seat_class(self):
        return self.seat.seat_class if self.seat else None


class BoardingPass(Base):
    __tablename__ = "boarding_passes"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)
    secure_token = Column(String, unique=True, nullable=False, index=True)
    signature = Column(String, nullable=True)
    used_at = Column(DateTime, nullable=True)
    checked_in_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    booking = relationship("Booking")


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    passenger_id = Column(Integer, ForeignKey("passengers.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="USD", nullable=False)
    card_token = Column(String, nullable=False)
    # tokenized reference only - never the full card number
    card_last4 = Column(String, nullable=False)
    status = Column(String, default="completed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SecurityIncident(Base):
    __tablename__ = "security_incidents"

    id = Column(Integer, primary_key=True)
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    incident_type = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, default="low", nullable=False)
    # low, medium, high, critical
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address = Column(String, nullable=True)
    status = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    prev_hash = Column(String, nullable=True)
    entry_hash = Column(String, nullable=True, index=True)
    # entry_hash = sha256(prev_hash + canonical fields) makes the log
    # chain tamper-evident: altering any past row breaks every hash after it.

    user = relationship("User", back_populates="audit_logs")
