from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user
from .schemas import PaymentRequest
from .models import User, Passenger, Booking, Flight, PaymentRecord
from .audit import log_security_event
from .security import mask_card_number
from .seat_routes import CLASS_PRICE_MULTIPLIER

router = APIRouter(prefix="/api/v1/payment", tags=["payment"])


@router.post("/process", status_code=status.HTTP_201_CREATED)
def process_payment(payload: PaymentRequest, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    passenger = db.query(Passenger).filter(Passenger.user_id == user.id).first()
    if not passenger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passenger profile not found")

    booking = db.query(Booking).filter(Booking.id == payload.booking_id, Booking.passenger_id == passenger.id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    flight = db.query(Flight).filter(Flight.id == booking.flight_id).first()
    if not flight:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")

    if db.query(PaymentRecord).filter(PaymentRecord.booking_id == booking.id, PaymentRecord.status == "completed").first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking has already been paid for")

    # PCI-DSS: the raw card number/expiry/CVC are used only in-memory for this
    # request and are never persisted, logged, or echoed back.
    token, last4 = mask_card_number(payload.card_number)

    # The charge amount is always derived server-side - never trust a
    # client-supplied amount (see Threat 5: payment manipulation). If the
    # booking has a real seat-map seat, the price reflects that seat's class;
    # otherwise it falls back to the flight's flat base price.
    if booking.seat is not None:
        amount = round(float(flight.base_price) * CLASS_PRICE_MULTIPLIER[booking.seat.seat_class], 2)
    else:
        amount = float(flight.base_price)

    record = PaymentRecord(
        booking_id=booking.id,
        passenger_id=passenger.id,
        amount=amount,
        card_token=token,
        card_last4=last4,
        status="completed",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    log_security_event(db, user.id, "PAYMENT_PROCESSED", "payment/process",
                        request.client.host if request.client else "unknown", "SUCCESS",
                        f"booking_id={booking.id} amount={record.amount} card=****{last4}")

    return {
        "payment_id": record.id,
        "status": record.status,
        "card_last4": record.card_last4,
        "amount": float(record.amount),
    }
