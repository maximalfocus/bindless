"""Shared fixtures: a live database connection and a client for the running secure application."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Connection, Engine

from bindless.db import create_db_engine, wait_until_ready
from bindless.scenarios import wait_for_health

SECURE_URL = os.environ.get("BINDLESS_SECURE_URL", "http://api-secure:8000")
VULNERABLE_URL = os.environ.get("BINDLESS_VULNERABLE_URL", "http://api-vulnerable:8000")
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    created = create_db_engine()
    wait_until_ready(created)
    yield created
    created.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as conn:
        yield conn


@pytest.fixture(scope="session")
def secure_client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=SECURE_URL, timeout=10.0) as client:
        wait_for_health(client)
        yield client


@pytest.fixture(scope="session")
def vulnerable_client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=VULNERABLE_URL, timeout=10.0) as client:
        wait_for_health(client)
        yield client
