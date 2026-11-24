from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user
from .models import User, Flight, Seat, Booking

router = APIRouter(prefix="/api/v1/flights", tags=["seats"])

SEAT_ROWS = 50
SEAT_LETTERS = ["A", "B", "C", "D", "E", "F"]
POSITION_BY_LETTER = {"A": "window", "B": "middle", "C": "aisle", "D": "aisle", "E": "middle", "F": "window"}
EXIT_ROWS = {13, 30}

CLASS_PRICE_MULTIPLIER = {"first": 3.0, "business": 1.8, "economy": 1.0}


def _seat_class_for_row(row: int) -> str:
    if row <= 4:
        return "first"
    if row <= 12:
        return "business"
    return "economy"


def _ensure_seats_generated(db: Session, flight: Flight) -> None:
    if db.query(Seat).filter(Seat.flight_id == flight.id).first():
        return  # already generated for this flight

    seats = []
    for row in range(1, SEAT_ROWS + 1):
        seat_class = _seat_class_for_row(row)
        for letter in SEAT_LETTERS:
            seats.append(Seat(
                flight_id=flight.id,
                seat_number=f"{row}{letter}",
                seat_class=seat_class,
                position=POSITION_BY_LETTER[letter],
                is_exit_row=row in EXIT_ROWS,
                # Last-row middle seats: tight to the galley/lavatory wall, no recline.
                is_restricted=(row == SEAT_ROWS and letter in ("B", "E")),
            ))
    db.add_all(seats)
    db.commit()


def _seat_price(flight: Flight, seat_class: str) -> float:
    return round(float(flight.base_price) * CLASS_PRICE_MULTIPLIER[seat_class], 2)


def available_seat_count(db: Session, flight: Flight) -> int:
    """Generates the seat map on first call for this flight, then returns how
    many seats are neither booked nor restricted. Used by the public flight
    list so search results show real availability, not a guess."""
    _ensure_seats_generated(db, flight)
    total = db.query(Seat).filter(Seat.flight_id == flight.id, Seat.is_restricted.is_(False)).count()
    booked = db.query(Booking).filter(
        Booking.flight_id == flight.id,
        Booking.status.in_(("active", "checkedin")),
        Booking.seat_id.isnot(None),
    ).count()
    return max(0, total - booked)


@router.get("/{flight_id}/seats")
def get_seat_map(flight_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")

    _ensure_seats_generated(db, flight)

    seats = db.query(Seat).filter(Seat.flight_id == flight_id).order_by(Seat.id).all()
    occupied_seat_ids = {
        b.seat_id for b in db.query(Booking).filter(
            Booking.flight_id == flight_id,
            Booking.status.in_(("active", "checkedin")),
            Booking.seat_id.isnot(None),
        ).all()
    }

    result = []
    for seat in seats:
        if seat.is_restricted:
            seat_status = "restricted"
        elif seat.id in occupied_seat_ids:
            seat_status = "occupied"
        else:
            seat_status = "available"

        result.append({
            "id": seat.id,
            "seat_number": seat.seat_number,
            "seat_class": seat.seat_class,
            "position": seat.position,
            "is_exit_row": seat.is_exit_row,
            "price": _seat_price(flight, seat.seat_class),
            "status": seat_status,
        })

    return {
        "flight_id": flight.id,
        "flight_number": flight.flight_number,
        "aircraft_id": flight.aircraft_id,
        "seats": result,
        "class_legend": {
            "first": {"rows": "1-4", "multiplier": CLASS_PRICE_MULTIPLIER["first"]},
            "business": {"rows": "5-12", "multiplier": CLASS_PRICE_MULTIPLIER["business"]},
            "economy": {"rows": "13-50", "multiplier": CLASS_PRICE_MULTIPLIER["economy"]},
        },
    }
