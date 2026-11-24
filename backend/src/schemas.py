from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List
import re

PASSPORT_REGEX = re.compile(r"^[A-Z0-9]{6,9}$")
PHONE_REGEX = re.compile(r"^\+?[1-9]\d{1,14}$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    requires_2fa: bool = False
    user_id: Optional[int] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TwoFactorVerifyRequest(BaseModel):
    user_id: int
    totp_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    passport_number: str
    address: Optional[str] = Field(default=None, max_length=200)
    date_of_birth: Optional[datetime] = None

    @field_validator("passport_number")
    @classmethod
    def validate_passport(cls, v: str) -> str:
        if not PASSPORT_REGEX.match(v):
            raise ValueError("Passport number must be 6-9 uppercase alphanumeric characters")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.match(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$", v):
            raise ValueError("Password must include uppercase, lowercase, number, and special character")
        return v


class UserProfile(BaseModel):
    id: int
    email: EmailStr
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlightSummary(BaseModel):
    id: int
    flight_number: str
    departure_time: datetime
    arrival_time: datetime
    from_airport: str
    to_airport: str
    gate: Optional[str] = None
    terminal: Optional[str] = None
    aircraft_id: Optional[str] = None
    base_price: float = 0
    status: str
    available_seats: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class BookingSummary(BaseModel):
    id: int
    flight_id: int
    seat_number: Optional[str]
    seat_class: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingCreateRequest(BaseModel):
    flight_id: int
    seat_id: Optional[int] = None
    # Preferred: an id from GET /flights/{id}/seats. Falls back to a plain
    # seat_number string (no seat-map pricing/class) if seat_id is omitted.
    seat_number: Optional[str] = Field(default=None, max_length=4)


class CheckinRequest(BaseModel):
    booking_id: int


class StaffCheckinRequest(BaseModel):
    boarding_pass_token: str = Field(min_length=10, max_length=128)


class PaymentRequest(BaseModel):
    booking_id: int
    card_number: str = Field(min_length=12, max_length=19)
    card_expiry: str = Field(min_length=4, max_length=5)
    card_cvc: str = Field(min_length=3, max_length=4)
    # No client-supplied amount: the charge is always derived server-side from
    # the booking's flight price (see Threat 5 - payment manipulation).

    @field_validator("card_number")
    @classmethod
    def validate_card_number(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if not (12 <= len(digits) <= 19):
            raise ValueError("Invalid card number")
        return v


class CreateStaffRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)
    role: str = Field(pattern="^(agent|crew|security|admin)$")
    department: Optional[str] = Field(default=None, max_length=100)
    employee_id: str = Field(min_length=2, max_length=50)


class SecurityIncidentCreate(BaseModel):
    incident_type: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=2000)
    severity: str = Field(pattern="^(low|medium|high|critical)$", default="low")


class SecurityIncidentSummary(BaseModel):
    id: int
    incident_type: str
    description: str
    severity: str
    timestamp: datetime
    resolved_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AuditLogSummary(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource: Optional[str]
    timestamp: datetime
    ip_address: Optional[str]
    status: str

    model_config = ConfigDict(from_attributes=True)
