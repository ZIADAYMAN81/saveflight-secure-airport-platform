"""One-off: point the seeded admin@example.com account at a real, Resend-verified
email address so its 2FA one-time-passcode email actually delivers (Resend's
sandbox mode only accepts sends to the account owner's own verified address,
not admin@example.com). Safe to run more than once - it's a no-op after the
first successful run.

Usage (from the backend/ directory, with DATABASE_URL etc. available in the
environment - e.g. via `railway run --service <saop-backend> -- python -m src.bootstrap_admin`):
"""
import os
from .database import SessionLocal
from .models import User

TARGET_EMAIL = os.environ["BOOTSTRAP_ADMIN_EMAIL"]


def run():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@example.com", User.role == "admin").first()
        if not admin:
            print("No admin@example.com account found - nothing to do.")
            return
        if admin.email == TARGET_EMAIL:
            print(f"admin account already uses {TARGET_EMAIL} - nothing to do.")
            return
        if db.query(User).filter(User.email == TARGET_EMAIL).first():
            print(f"A user with email {TARGET_EMAIL} already exists - not overwriting. Aborting.")
            return
        admin.email = TARGET_EMAIL
        db.commit()
        print(f"Updated admin account email to {TARGET_EMAIL}. Existing TOTP secret and role are unchanged.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
