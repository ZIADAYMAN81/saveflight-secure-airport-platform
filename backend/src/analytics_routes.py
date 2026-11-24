"""Admin analytics: every number here is computed from real rows already in
the database (bookings, boarding passes, payments, flights, audit logs).
Metrics with no real data source behind them - check-in queue wait times,
"staff needs assistance" alerts, a fabricated uptime percentage - are
deliberately left out rather than invented; use /metrics + Grafana for actual
uptime/latency monitoring (see infrastructure/prometheus).
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .database import get_db
from .deps import require_role
from .models import User, Staff, Flight, Booking, BoardingPass, PaymentRecord, AuditLog

router = APIRouter(prefix="/api/v1/admin/analytics", tags=["admin-analytics"],
                    dependencies=[Depends(require_role(["admin"]))])

AIRLINE_CODE_RE = re.compile(r"^[A-Z]{2,3}")


def _airline_code(flight_number: str) -> str:
    match = AIRLINE_CODE_RE.match(flight_number or "")
    return match.group(0) if match else "??"


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1)

    flights_today = db.query(Flight).filter(
        Flight.departure_time >= today_start, Flight.departure_time < today_end
    ).count()

    checkins_today = db.query(BoardingPass).filter(
        BoardingPass.created_at >= today_start, BoardingPass.created_at < today_end
    ).count()

    revenue_today = db.query(PaymentRecord).filter(
        PaymentRecord.created_at >= today_start, PaymentRecord.created_at < today_end,
        PaymentRecord.status == "completed",
    ).all()
    revenue_today_total = round(sum(float(p.amount) for p in revenue_today), 2)

    # Real, but named for what it actually measures: elapsed time from booking
    # creation to check-in completion - not a queue/wait-time metric (that data
    # doesn't exist anywhere in this system).
    pairs = db.query(Booking.created_at, BoardingPass.created_at).join(
        BoardingPass, BoardingPass.booking_id == Booking.id
    ).all()
    if pairs:
        avg_seconds = sum((bp - bk).total_seconds() for bk, bp in pairs) / len(pairs)
        avg_booking_to_checkin_minutes = round(avg_seconds / 60, 1)
    else:
        avg_booking_to_checkin_minutes = None

    active_staff = db.query(User).filter(User.role != "passenger", User.is_active.is_(True)).count()

    return {
        "flights_today": flights_today,
        "checkins_today": checkins_today,
        "revenue_today": revenue_today_total,
        "avg_booking_to_checkin_minutes": avg_booking_to_checkin_minutes,
        "active_staff": active_staff,
        "monitoring_note": "Real uptime/latency metrics are exposed at /metrics (Prometheus format) - see the Grafana dashboard, not a value fabricated here.",
    }


@router.get("/hourly-checkins")
def hourly_checkins(hours: int = 24, db: Session = Depends(get_db)):
    hours = min(max(hours, 1), 168)
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = db.query(BoardingPass.created_at).filter(BoardingPass.created_at >= since).all()

    buckets = defaultdict(int)
    for (created_at,) in rows:
        bucket = created_at.replace(minute=0, second=0, microsecond=0)
        buckets[bucket] += 1

    return sorted(
        [{"hour": hour.isoformat(), "count": count} for hour, count in buckets.items()],
        key=lambda r: r["hour"],
    )


@router.get("/passengers-by-terminal")
def passengers_by_terminal(db: Session = Depends(get_db)):
    """Real, but sparse: `terminal` is a newer field and most seeded flights
    predate it, so many will land in "Unassigned" until it's backfilled."""
    rows = db.query(Flight.terminal).join(
        Booking, Booking.flight_id == Flight.id
    ).join(BoardingPass, BoardingPass.booking_id == Booking.id).all()

    counts = defaultdict(int)
    for (terminal,) in rows:
        counts[terminal or "Unassigned"] += 1

    return [{"terminal": terminal, "passengers": count} for terminal, count in counts.items()]


@router.get("/popular-routes")
def popular_routes(limit: int = 10, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 50)
    rows = db.query(Booking.flight_id, Flight.from_airport, Flight.to_airport).join(
        Flight, Flight.id == Booking.flight_id
    ).all()

    counts = defaultdict(int)
    for _, frm, to in rows:
        counts[(frm, to)] += 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"from_airport": frm, "to_airport": to, "bookings": count} for (frm, to), count in ranked]


@router.get("/revenue-by-airline")
def revenue_by_airline(db: Session = Depends(get_db)):
    rows = db.query(PaymentRecord.amount, Flight.flight_number).join(
        Booking, Booking.id == PaymentRecord.booking_id
    ).join(Flight, Flight.id == Booking.flight_id).filter(PaymentRecord.status == "completed").all()

    totals = defaultdict(float)
    for amount, flight_number in rows:
        totals[_airline_code(flight_number)] += float(amount)

    return sorted(
        [{"airline": code, "revenue": round(total, 2)} for code, total in totals.items()],
        key=lambda r: r["revenue"], reverse=True,
    )


@router.get("/realtime")
def realtime(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    soon = now + timedelta(hours=2)

    departing_soon = db.query(Flight).filter(
        Flight.departure_time >= now, Flight.departure_time <= soon,
        Flight.status.in_(("scheduled", "boarding")),
    ).count()

    gates_in_use = db.query(Flight.gate).filter(
        Flight.status.in_(("boarding", "departed")), Flight.gate.isnot(None),
    ).distinct().count()

    # Checked in but not yet boarded, on a flight that hasn't departed yet.
    passengers_in_terminal = db.query(BoardingPass).join(
        Booking, Booking.id == BoardingPass.booking_id
    ).join(Flight, Flight.id == Booking.flight_id).filter(
        BoardingPass.used_at.is_(None),
        Flight.status.in_(("scheduled", "boarding")),
    ).count()

    staff_rows = db.query(Staff.department, User.is_active).join(User, User.id == Staff.user_id).all()
    staff_by_department = defaultdict(int)
    for department, is_active in staff_rows:
        if is_active:
            staff_by_department[department or "Unassigned"] += 1

    return {
        "flights_departing_next_2h": departing_soon,
        "gates_in_use": gates_in_use,
        "passengers_in_terminal": passengers_in_terminal,
        "staff_by_department": dict(staff_by_department),
    }


@router.get("/activity-feed")
def activity_feed(limit: int = 30, db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 100)
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [
        {"id": l.id, "action": l.action, "resource": l.resource, "status": l.status,
         "timestamp": l.timestamp.isoformat(), "user_id": l.user_id}
        for l in logs
    ]


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    since = now - timedelta(hours=24)
    result = []

    delayed = db.query(Flight).filter(
        Flight.status.in_(("scheduled", "boarding")), Flight.departure_time < now,
    ).all()
    for flight in delayed:
        result.append({
            "type": "flight_delay", "severity": "medium",
            "message": f"{flight.flight_number} has not departed on its scheduled time.",
        })

    # Repeated failed logins/lockouts in the last 24h - a real, derivable security signal.
    failed_rows = db.query(AuditLog.user_id).filter(
        AuditLog.action.in_(("LOGIN_FAILED", "2FA_FAILED")), AuditLog.timestamp >= since,
    ).all()
    counts = defaultdict(int)
    for (user_id,) in failed_rows:
        if user_id is not None:
            counts[user_id] += 1
    for user_id, count in counts.items():
        if count >= 3:
            result.append({
                "type": "repeated_auth_failures", "severity": "high",
                "message": f"User #{user_id} has {count} failed login/2FA attempts in the last 24h.",
            })

    return result
