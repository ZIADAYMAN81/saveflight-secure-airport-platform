import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# `Base.metadata.create_all()` only creates missing *tables* - it never alters
# an existing table's columns. There's no Alembic setup for this project's
# scale, so new nullable columns are added here idempotently on startup
# instead of via a full migration framework.
_ADDITIVE_COLUMNS = {
    "users": [
        ("email_otp_hash", "VARCHAR"),
        ("email_otp_expires_at", "TIMESTAMP"),
    ],
    "flights": [
        ("terminal", "VARCHAR"),
    ],
    "bookings": [
        ("seat_id", "INTEGER"),
    ],
    "boarding_passes": [
        ("signature", "VARCHAR"),
    ],
}


def run_lightweight_migrations():
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if not inspector.has_table(table):
                continue  # create_all() will create it fresh with all current columns
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, col_type in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
