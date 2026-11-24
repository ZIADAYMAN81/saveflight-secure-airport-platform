import hashlib
from sqlalchemy.orm import Session
from .models import AuditLog

GENESIS_HASH = "0" * 64


def _compute_hash(prev_hash: str, user_id, action: str, resource: str, ip_address: str, status: str, details: str, timestamp) -> str:
    payload = "|".join([
        prev_hash,
        str(user_id or ""),
        action or "",
        resource or "",
        ip_address or "",
        status or "",
        details or "",
        timestamp.isoformat(),
    ])
    return hashlib.sha256(payload.encode()).hexdigest()


def log_security_event(db: Session, user_id, action: str, resource: str, ip_address: str, status: str, details: str = ""):
    """Append a tamper-evident audit event.

    Each row's entry_hash commits to the previous row's hash, so editing or
    deleting any historical row invalidates every entry_hash that follows it.
    """
    last = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last.entry_hash if last and last.entry_hash else GENESIS_HASH

    from datetime import datetime
    timestamp = datetime.utcnow()
    entry_hash = _compute_hash(prev_hash, user_id, action, resource, ip_address, status, details, timestamp)

    event = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        ip_address=ip_address,
        status=status,
        details=details,
        timestamp=timestamp,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def verify_chain_integrity(db: Session) -> bool:
    """Recompute the hash chain to detect tampering with historical logs."""
    prev_hash = GENESIS_HASH
    for entry in db.query(AuditLog).order_by(AuditLog.id.asc()).all():
        expected = _compute_hash(
            prev_hash, entry.user_id, entry.action, entry.resource,
            entry.ip_address, entry.status, entry.details, entry.timestamp,
        )
        if entry.prev_hash != prev_hash or entry.entry_hash != expected:
            return False
        prev_hash = entry.entry_hash
    return True
