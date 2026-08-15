"""Database engine construction and a bounded readiness probe."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from bindless.config import get_settings


def create_db_engine(database_url: str | None = None) -> Engine:
    url = database_url if database_url is not None else get_settings().database_url
    return create_engine(url, pool_pre_ping=True, future=True)


def wait_until_ready(engine: Engine, *, attempts: int = 60, delay_seconds: float = 0.5) -> None:
    """Poll the database until it accepts a trivial query, or raise the last error.

    Compose's healthcheck already gates startup; this covers the short window in which PostgreSQL
    reports healthy while still finishing first-run initialization.
    """
    last_error: OperationalError | None = None
    for _ in range(attempts):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except OperationalError as error:  # pragma: no cover - timing dependent
            last_error = error
            time.sleep(delay_seconds)
        else:
            return
    if last_error is not None:  # pragma: no cover - timing dependent
        raise last_error


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
