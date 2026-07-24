"""SQLite Database session and initialization for AutoQA Enterprise."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = _BACKEND_ROOT / os.getenv("AGENT_DB", "autoqa_enterprise.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all database tables on startup."""
    from app.db import models_db  # noqa: F401
    Base.metadata.create_all(bind=engine)
