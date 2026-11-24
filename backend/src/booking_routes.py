from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user
from .schemas import BookingCreateRequest, BookingSummary
from .models import User, Passenger, Flight, Booking, Seat
from .audit import log_security_event

router = APIRouter(prefix="/api/v1/booking", tags=["booking"])


def _seat_taken(db: Session, flight_id: int, seat_id: int) -> bool:
    return db.query(Booking).filter(
        Booking.flight_id == flight_id,
        Booking.seat_id == seat_id,
        Booking.status.in_(("active", "checkedin")),
    ).first() is not None


@router.post("/create", response_model=BookingSummary, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreateRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    passenger = db.query(Passenger).filter(Passenger.user_id == user.id).first()
    if not passenger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passenger profile not found")

    flight = db.query(Flight).filter(Flight.id == payload.flight_id).first()
    if not flight or flight.status not in ("scheduled", "boarding"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Flight is not available for booking")

    seat_id = None
    seat_number = payload.seat_number

    if payload.seat_id is not None:
        seat = db.query(Seat).filter(Seat.id == payload.seat_id, Seat.flight_id == flight.id).first()
        if not seat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seat not found on this flight")
        if seat.is_restricted:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seat is restricted and cannot be booked")
        if _seat_taken(db, flight.id, seat.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seat already assigned on this flight")
        seat_id = seat.id
        seat_number = seat.seat_number
    elif payload.seat_number:
        # Legacy path: free-text seat, no seat map/class - still collision-checked.
        seat_taken = db.query(Booking).filter(
            Booking.flight_id == flight.id,
            Booking.seat_number == payload.seat_number,
            Booking.status.in_(("active", "checkedin")),
        ).first()
        if seat_taken:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seat already assigned on this flight")

    booking = Booking(
        passenger_id=passenger.id,
        flight_id=flight.id,
        seat_id=seat_id,
        seat_number=seat_number,
        status="active",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    log_security_event(db, user.id, "BOOKING_CREATED", "booking/create",
                        request.client.host if request.client else "unknown", "SUCCESS", f"flight_id={flight.id}")
    return booking
