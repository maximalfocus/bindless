"""Nothing the endpoint can be asked to do changes a byte of the fixture data."""

from __future__ import annotations

import httpx
from sqlalchemy import Connection, Engine

from bindless import fixtures
from bindless.payloads import TAUTOLOGY, UNION_CREDENTIALS
from bindless.scenarios import run_secure_walkthrough
from bindless.state import DOMAIN_TABLES, domain_state_digest

HOSTILE_INPUT = [
    {"supplier": TAUTOLOGY},
    {"supplier": UNION_CREDENTIALS},
    {"supplier": "Kestrel Logistics", "sort": "api_key"},
    {"supplier": "'", "sort": "amount"},
    {"supplier": "%", "sort": "status"},
]


def _digest(engine: Engine) -> str:
    with engine.connect() as connection:
        return domain_state_digest(connection)


def test_the_full_walkthrough_leaves_state_byte_for_byte_identical(
    secure_client: httpx.Client, engine: Engine
) -> None:
    before = _digest(engine)
    outcomes = run_secure_walkthrough(secure_client)
    assert outcomes  # the walkthrough actually ran
    assert _digest(engine) == before


def test_hostile_input_leaves_state_byte_for_byte_identical(
    secure_client: httpx.Client, engine: Engine
) -> None:
    before = _digest(engine)
    headers = {"Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}"}
    for params in HOSTILE_INPUT:
        secure_client.get("/invoices", params=params, headers=headers)
    assert _digest(engine) == before


def test_row_counts_match_the_fixtures_exactly(connection: Connection) -> None:
    from sqlalchemy import text

    expected = {
        "organizations": len(fixtures.ORGANIZATIONS),
        "users": len(fixtures.USERS),
        "suppliers": len(fixtures.SUPPLIERS),
        "invoices": len(fixtures.INVOICES),
        "integration_credentials": len(fixtures.INTEGRATION_CREDENTIALS),
    }
    assert set(expected) == set(DOMAIN_TABLES)
    for table, count in expected.items():
        actual = connection.execute(
            text(f"SELECT count(*) FROM {table}")  # noqa: S608 - fixed table allowlist
        ).scalar_one()
        assert actual == count, table


def test_the_digest_is_stable_across_repeated_reads(engine: Engine) -> None:
    assert _digest(engine) == _digest(engine)
