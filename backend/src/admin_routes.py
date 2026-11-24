from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, status
from sqlalchemy.orm import Session
from .database import get_db
from .deps import get_current_user, require_role
from .schemas import CreateStaffRequest, UserProfile, AuditLogSummary
from .models import User, Staff, AuditLog
from .audit import log_security_event, verify_chain_integrity
from .security import hash_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=List[UserProfile])
def list_users(user: User = Depends(require_role(["admin"])), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/create-staff", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def create_staff(payload: CreateStaffRequest, request: Request, admin: User = Depends(require_role(["admin"])), db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A user with this email already exists")
    if db.query(Staff).filter(Staff.employee_id == payload.employee_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee ID already in use")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    staff = Staff(
        user_id=user.id,
        full_name=payload.full_name,
        department=payload.department,
        employee_id=payload.employee_id,
    )
    db.add(staff)

    log_security_event(db, admin.id, "STAFF_CREATED", "admin/create-staff",
                        request.client.host if request.client else "unknown", "SUCCESS",
                        f"new_user_id={user.id} role={payload.role}")
    return user


@router.get("/audit-logs", response_model=List[AuditLogSummary])
def audit_logs(limit: int = 100, admin: User = Depends(require_role(["admin"])), db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 500)
    return db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()


@router.get("/audit-logs/verify")
def audit_logs_verify(admin: User = Depends(require_role(["admin"])), db: Session = Depends(get_db)):
    """Recomputes the audit-log hash chain to confirm no historical entry has been tampered with."""
    return {"intact": verify_chain_integrity(db)}


@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: int, request: Request, admin: User = Depends(require_role(["admin"])), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.is_active = False
    db.commit()
    log_security_event(db, admin.id, "USER_DEACTIVATED", "admin/users", request.client.host if request.client else "unknown", "SUCCESS", f"target_user_id={user_id}")
    return {"message": "User deactivated"}
