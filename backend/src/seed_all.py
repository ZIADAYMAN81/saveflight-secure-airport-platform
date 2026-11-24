"""Runs baseline init_db seeding followed by the richer demo dataset in one
process - avoids relying on shell operators (&&) in a preDeployCommand.
Run: python -m src.seed_all
"""
from .init_db import initialize_database
from .seed_demo_data import seed


if __name__ == "__main__":
    initialize_database()
    seed()
