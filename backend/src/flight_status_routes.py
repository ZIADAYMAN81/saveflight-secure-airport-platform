"""Flight status/timeline endpoint.

There is no real ADS-B/position feed anywhere in this system - "live" position,
altitude, and speed below are DETERMINISTICALLY SIMULATED from the flight's
stored departure/arrival times and airport coordinates, and the response says
so explicitly (`"simulated": true`). Timeline stage completion and delay
detection, however, are real - they're computed from the actual stored
timestamps and current status.
"""
import math
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user
from .models import User, Flight

router = APIRouter(prefix="/api/v1/flights", tags=["flight-status"])

# Approximate airport coordinates (lat, lon) for the routes this demo uses.
AIRPORT_COORDS = {
    "CAI": (30.1219, 31.4056), "JFK": (40.6413, -73.7781), "DXB": (25.2532, 55.3657),
    "LHR": (51.4700, -0.4543), "FRA": (50.0379, 8.5622), "JED": (21.6796, 39.1565),
    "DOH": (25.2731, 51.6081), "IST": (41.2753, 28.7519), "CDG": (49.0097, 2.5479),
    "AUH": (24.4330, 54.6511), "RUH": (24.9576, 46.6988), "YVR": (49.1967, -123.1815),
    "LAX": (33.9416, -118.4085),
}
EARTH_RADIUS_KM = 6371.0


def _haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _interpolate(a, b, fraction):
    return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)


def _simulated_flight_profile(fraction: float, cruise_altitude_ft: int = 38000, cruise_speed_kts: int = 520):
    """Simple climb/cruise/descend curve as a function of elapsed-flight fraction [0,1]."""
    if fraction < 0.15:
        ramp = fraction / 0.15
        return round(cruise_altitude_ft * ramp), round(cruise_speed_kts * (0.4 + 0.6 * ramp))
    if fraction > 0.85:
        ramp = (1 - fraction) / 0.15
        return round(cruise_altitude_ft * ramp), round(cruise_speed_kts * (0.4 + 0.6 * ramp))
    return cruise_altitude_ft, cruise_speed_kts


@router.get("/{flight_id}/status")
def get_flight_status(flight_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if not flight:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")

    now = datetime.utcnow()
    boarding_time = flight.departure_time - timedelta(minutes=45)
    pushback_time = flight.departure_time - timedelta(minutes=15)

    def stage(name, at, done_if_status=None):
        completed = now >= at or (done_if_status and flight.status in done_if_status)
        return {"name": name, "at": at.isoformat(), "completed": completed}

    timeline = [
        stage("scheduled", flight.departure_time - timedelta(hours=2)),
        stage("boarding", boarding_time, done_if_status=("boarding", "departed", "landed")),
        stage("pushback", pushback_time, done_if_status=("departed", "landed")),
        stage("departed", flight.departure_time, done_if_status=("departed", "landed")),
        stage("arrived", flight.arrival_time, done_if_status=("landed",)),
    ]

    alerts = []
    if flight.status in ("scheduled", "boarding") and now > flight.departure_time:
        alerts.append({"type": "delay", "message": "This flight has not departed on its scheduled time."})
    if flight.status == "boarding" and flight.departure_time - now < timedelta(minutes=10):
        alerts.append({"type": "final_call", "message": f"Boarding closes soon for {flight.flight_number} at gate {flight.gate or 'TBA'}."})

    live = None
    if flight.status == "departed":
        origin = AIRPORT_COORDS.get(flight.from_airport)
        dest = AIRPORT_COORDS.get(flight.to_airport)
        total_seconds = (flight.arrival_time - flight.departure_time).total_seconds()
        elapsed_seconds = max(0, (now - flight.departure_time).total_seconds())
        fraction = min(1.0, elapsed_seconds / total_seconds) if total_seconds > 0 else 1.0

        altitude_ft, speed_kts = _simulated_flight_profile(fraction)
        live = {
            "simulated": True,
            "note": "Position/altitude/speed are simulated from scheduled times - no real ADS-B feed is connected.",
            "progress_fraction": round(fraction, 3),
            "altitude_ft": altitude_ft,
            "speed_kts": speed_kts,
        }
        if origin and dest:
            position = _interpolate(origin, dest, fraction)
            total_distance_km = _haversine_km(origin, dest)
            live.update({
                "position": {"lat": round(position[0], 4), "lon": round(position[1], 4)},
                "distance_remaining_km": round(total_distance_km * (1 - fraction)),
                "time_to_destination_minutes": round((total_seconds * (1 - fraction)) / 60),
            })

    return {
        "flight_id": flight.id,
        "flight_number": flight.flight_number,
        "status": flight.status,
        "from_airport": flight.from_airport,
        "to_airport": flight.to_airport,
        "gate": flight.gate,
        "terminal": flight.terminal,
        "aircraft_id": flight.aircraft_id,
        "timeline": timeline,
        "alerts": alerts,
        "live": live,
    }
