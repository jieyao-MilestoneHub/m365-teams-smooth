"""Database engine and session factory, driven by ``DB_URL`` (SQLite now, Postgres later).

Schema is created with ``Base.metadata.create_all`` for the SQLite-first local setup; Alembic
migrations are tracked as a follow-up. The session factory is injected into the repositories.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import Base

SessionFactory = Callable[[], Session]


def make_engine(db_url: str) -> Engine:
    """Create an engine for ``db_url``, ensuring a local SQLite file's directory exists."""
    prefix = "sqlite:///"
    if db_url.startswith(prefix):
        path = db_url[len(prefix) :]
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    return create_engine(db_url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to ``engine``."""
    return sessionmaker(bind=engine)


def init_db(engine: Engine) -> None:
    """Create all tables if they do not exist (SQLite-first; Alembic is a follow-up)."""
    Base.metadata.create_all(engine)
