from datetime import datetime, timedelta, time
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user, require_role
from .schemas import StaffCheckinRequest, SecurityIncidentCreate, SecurityIncidentSummary
from .models import User, Booking, BoardingPass, Flight, Passenger, SecurityIncident
from .audit import log_security_event
from .security import decrypt_data, boarding_pass_payload, verify_boarding_pass_signature

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])

STAFF_ROLES = ["agent", "crew", "security", "admin"]


@router.get("/dashboard")
def staff_dashboard(user: User = Depends(require_role(STAFF_ROLES)), db: Session = Depends(get_db)):
    today_start = datetime.combine(datetime.utcnow().date(), time.min)
    today_end = today_start + timedelta(days=1)

    flights_today = db.query(Flight).filter(
        Flight.departure_time >= today_start, Flight.departure_time < today_end
    ).count()
    checkins_completed = db.query(BoardingPass).filter(BoardingPass.used_at.isnot(None)).count()
    pending = db.query(Booking).filter(Booking.status == "checkedin").count()

    return {
        "flights_today": flights_today,
        "checkins_completed": checkins_completed,
        "pending_boarding": pending,
        "role": user.role,
    }


@router.post("/checkin-passenger")
def staff_checkin_passenger(payload: StaffCheckinRequest, request: Request,
                             user: User = Depends(require_role(["agent", "admin"])),
                             db: Session = Depends(get_db)):
    """Check-in agents (or admins) redeem a passenger's boarding pass at the gate."""
    pass_record = db.query(BoardingPass).filter(BoardingPass.secure_token == payload.boarding_pass_token).first()
    if not pass_record:
        log_security_event(db, user.id, "STAFF_CHECKIN_INVALID_TOKEN", "staff/checkin-passenger",
                            request.client.host if request.client else "unknown", "FAILED")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Boarding pass not found")

    if pass_record.used_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Boarding pass already used")

    # Independent cryptographic check, on top of (not instead of) the DB
    # lookup above: recompute the signed payload from the booking this pass
    # actually points to right now, and verify it against the RSA signature
    # captured at issuance. A pass whose underlying booking row was altered
    # directly (bypassing the app - e.g. a compromised DB credential editing
    # flight_id or seat_number after issuance) fails this check even though
    # the token itself still matches, since the signature commits to the
    # original values, not whatever the row currently says.
    booking = db.query(Booking).filter(Booking.id == pass_record.booking_id).first()
    payload = boarding_pass_payload(booking.id, pass_record.secure_token, booking.flight_id, booking.seat_number)
    if not pass_record.signature or not verify_boarding_pass_signature(payload, pass_record.signature):
        log_security_event(db, user.id, "STAFF_CHECKIN_SIGNATURE_INVALID", "staff/checkin-passenger",
                            request.client.host if request.client else "unknown", "FAILED",
                            f"boarding_pass_id={pass_record.id}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Boarding pass failed integrity verification")

    pass_record.used_at = datetime.utcnow()
    pass_record.checked_in_by = user.id
    db.commit()

    log_security_event(db, user.id, "STAFF_CHECKIN_SUCCESS", "staff/checkin-passenger",
                        request.client.host if request.client else "unknown", "SUCCESS",
                        f"boarding_pass_id={pass_record.id}")
    return {"success": True, "message": "Passenger checked in"}


@router.get("/flights/{flight_id}/manifest")
def flight_manifest(flight_id: int, user: User = Depends(require_role(["crew", "admin"])), db: Session = Depends(get_db)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")

    bookings = db.query(Booking).filter(Booking.flight_id == flight_id).all()
    manifest = []
    for booking in bookings:
        passenger = db.query(Passenger).filter(Passenger.id == booking.passenger_id).first()
        if not passenger:
            continue
        manifest.append({
            "booking_id": booking.id,
            "passenger_name": decrypt_data(passenger.full_name),
            "seat_number": booking.seat_number,
            "status": booking.status,
        })
    return {"flight_number": flight.flight_number, "manifest": manifest}


@router.post("/incidents", response_model=SecurityIncidentSummary, status_code=status.HTTP_201_CREATED)
def report_incident(payload: SecurityIncidentCreate, user: User = Depends(require_role(["security", "admin"])), db: Session = Depends(get_db)):
    incident = SecurityIncident(
        reported_by=user.id,
        incident_type=payload.incident_type,
        description=payload.description,
        severity=payload.severity,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("/incidents", response_model=List[SecurityIncidentSummary])
def list_incidents(user: User = Depends(require_role(["security", "admin"])), db: Session = Depends(get_db)):
    return db.query(SecurityIncident).order_by(SecurityIncident.timestamp.desc()).all()
