"""
Database Connection & Session Configuration.
Supports SQLite by default (zero-setup relational SQL file)
and seamlessly switches to PostgreSQL / MySQL via DATABASE_URL environment variable.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Path configuration
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB_PATH = DATA_DIR / "timetable.db"
DEFAULT_SQLITE_URL = f"sqlite:///{SQLITE_DB_PATH.as_posix()}"

# Read from environment or default to SQLite
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)

# Configure Engine
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,  # Set to True for debugging SQL queries
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI Dependency for database session injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Creates all database tables defined in db_models."""
    from app import db_models  # Ensure models are loaded
    Base.metadata.create_all(bind=engine)
