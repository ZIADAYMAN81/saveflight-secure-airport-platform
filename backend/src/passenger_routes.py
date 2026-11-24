import secrets
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user
from .schemas import UserProfile, FlightSummary, BookingSummary, CheckinRequest
from .models import User, Passenger, Flight, Booking, BoardingPass
from .audit import log_security_event
from .security import decrypt_data, sign_boarding_pass, boarding_pass_payload, boarding_pass_public_key_pem
from .seat_routes import available_seat_count

router = APIRouter(prefix="/api/v1", tags=["passenger"])


def _serialize_flight(db: Session, f: Flight) -> dict:
    return {
        "id": f.id, "flight_number": f.flight_number, "departure_time": f.departure_time,
        "arrival_time": f.arrival_time, "from_airport": f.from_airport, "to_airport": f.to_airport,
        "gate": f.gate, "terminal": f.terminal, "aircraft_id": f.aircraft_id,
        "base_price": float(f.base_price), "status": f.status,
        "available_seats": available_seat_count(db, f),
    }


@router.get("/flights/{flight_id}", response_model=FlightSummary)
def get_flight(flight_id: int, db: Session = Depends(get_db)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")
    return _serialize_flight(db, flight)


@router.get("/flights", response_model=List[FlightSummary])
def list_flights(
    from_airport: Optional[str] = None,
    to_airport: Optional[str] = None,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Public endpoint: minimal, non-sensitive flight schedule data only.
    Only ever returns flights that are actually still bookable/trackable
    (excludes cancelled) - "show only available flights" is enforced here,
    server-side, not left to the client to filter."""
    query = db.query(Flight).filter(Flight.status != "cancelled")
    if from_airport:
        query = query.filter(Flight.from_airport == from_airport.upper())
    if to_airport:
        query = query.filter(Flight.to_airport == to_airport.upper())
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date must be YYYY-MM-DD")
        query = query.filter(Flight.departure_time >= day, Flight.departure_time < day + timedelta(days=1))

    flights = query.order_by(Flight.departure_time).all()
    return [_serialize_flight(db, f) for f in flights]


@router.get("/passenger/profile", response_model=UserProfile)
def passenger_profile(user: User = Depends(get_current_user)):
    return user


@router.get("/passenger/bookings", response_model=List[BookingSummary])
def passenger_bookings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    passenger = db.query(Passenger).filter(Passenger.user_id == user.id).first()
    if not passenger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passenger profile not found")
    # Row-level security: only this passenger's own bookings are ever queried/returned.
    bookings = db.query(Booking).filter(Booking.passenger_id == passenger.id).order_by(Booking.created_at.desc()).all()
    return bookings


@router.post("/passenger/checkin")
def passenger_checkin(payload: CheckinRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    passenger = db.query(Passenger).filter(Passenger.user_id == user.id).first()
    if not passenger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passenger profile not found")

    booking = db.query(Booking).filter(Booking.id == payload.booking_id, Booking.passenger_id == passenger.id).first()
    if not booking or booking.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking cannot be checked in")

    existing = db.query(BoardingPass).filter(BoardingPass.booking_id == booking.id).first()
    if existing and existing.used_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Boarding pass already used")

    if not existing:
        secure_token = secrets.token_urlsafe(32)
        payload = boarding_pass_payload(booking.id, secure_token, booking.flight_id, booking.seat_number)
        signature = sign_boarding_pass(payload)
        boarding_pass = BoardingPass(booking_id=booking.id, secure_token=secure_token, signature=signature)
        db.add(boarding_pass)
        booking.status = "checkedin"
        db.commit()
        db.refresh(boarding_pass)
    else:
        boarding_pass = existing

    log_security_event(db, user.id, "CHECKIN_CREATED", "passenger/checkin",
                        request.client.host if request.client else "unknown", "SUCCESS", f"booking_id={booking.id}")
    return {
        "boarding_pass_token": boarding_pass.secure_token,
        "signature": boarding_pass.signature,
        "flight_id": booking.flight_id,
        "seat_number": booking.seat_number,
        "status": "checked_in",
    }


@router.get("/boarding-pass/public-key")
def get_boarding_pass_public_key():
    """Public key for independently verifying a boarding pass's RSA signature.
    Deliberately unauthenticated - public keys are meant to be shared freely;
    only the private key (never exposed here) must stay secret."""
    return {"algorithm": "RSA-2048 / PSS / SHA-256", "public_key_pem": boarding_pass_public_key_pem()}


@router.get("/passenger/boarding-pass/{token}")
def boarding_pass(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pass_record = db.query(BoardingPass).filter(BoardingPass.secure_token == token).first()
    if not pass_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Boarding pass not found")

    booking = db.query(Booking).filter(Booking.id == pass_record.booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    passenger = db.query(Passenger).filter(Passenger.id == booking.passenger_id, Passenger.user_id == user.id).first()
    if not passenger:
        # Not this user's boarding pass - do not confirm whether the token exists.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    flight = db.query(Flight).filter(Flight.id == booking.flight_id).first()
    if not flight:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")

    return {
        "passenger_name": decrypt_data(passenger.full_name),
        "flight_number": flight.flight_number,
        "from_airport": flight.from_airport,
        "to_airport": flight.to_airport,
        "departure_time": flight.departure_time,
        "arrival_time": flight.arrival_time,
        "gate": flight.gate,
        "seat_number": booking.seat_number,
        "status": booking.status,
        "used": pass_record.used_at is not None,
        "secure_token": pass_record.secure_token,
    }
