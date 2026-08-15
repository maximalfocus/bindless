"""The vulnerable application actually is vulnerable, in exactly the three intended ways.

If any of these ever started passing "securely", the demonstration would be showing a fix that
isn't there. So the vulnerability itself is under test.
"""

from __future__ import annotations

import httpx
import pytest

from bindless import fixtures
from bindless.api import EFFECTIVE_QUERY_HEADER
from bindless.payloads import CREDENTIAL_MARKER, SORT_IDENTIFIER, TAUTOLOGY, UNION_CREDENTIALS
from bindless.scenarios import find_credentials, own_invoice_numbers

ACTOR_TOKEN = fixtures.DEMO_ACTOR_TOKEN
BENIGN_SUPPLIER = fixtures.DEMO_BENIGN_SUPPLIER


def _list(
    client: httpx.Client, *, supplier: str, token: str = ACTOR_TOKEN, sort: str | None = None
) -> httpx.Response:
    params: dict[str, str] = {"supplier": supplier}
    if sort is not None:
        params["sort"] = sort
    return client.get("/invoices", params=params, headers={"Authorization": f"Bearer {token}"})


def test_benign_search_still_works_on_the_vulnerable_app(vulnerable_client: httpx.Client) -> None:
    response = _list(vulnerable_client, supplier=BENIGN_SUPPLIER, sort="i.amount DESC")
    assert response.status_code == httpx.codes.OK
    numbers = [row["invoice_number"] for row in response.json()["invoices"]]
    assert numbers == ["INV-1003", "INV-1001", "INV-1002"]


def test_tautology_breaks_tenant_isolation(vulnerable_client: httpx.Client) -> None:
    response = _list(vulnerable_client, supplier=TAUTOLOGY)
    assert response.status_code == httpx.codes.OK
    numbers = {row["invoice_number"] for row in response.json()["invoices"]}
    # The caller is org 1, yet other organizations' invoices come back.
    assert numbers & own_invoice_numbers(2)
    assert numbers & own_invoice_numbers(3)


def test_union_payload_exfiltrates_credentials(vulnerable_client: httpx.Client) -> None:
    response = _list(vulnerable_client, supplier=UNION_CREDENTIALS)
    assert response.status_code == httpx.codes.OK
    leaked = find_credentials(response.json())
    assert leaked
    assert all(CREDENTIAL_MARKER in value for value in leaked)


def test_sort_injection_reaches_the_order_by_clause(vulnerable_client: httpx.Client) -> None:
    # A crafted ORDER BY that sorts by a correlated subquery changes the row order in a way only an
    # injected identifier could. Ascending vs descending on the same expression must differ.
    ascending = _list(
        vulnerable_client,
        supplier=BENIGN_SUPPLIER,
        sort="(SELECT count(*) FROM invoices x WHERE x.amount <= i.amount) ASC",
    )
    descending = _list(
        vulnerable_client,
        supplier=BENIGN_SUPPLIER,
        sort="(SELECT count(*) FROM invoices x WHERE x.amount <= i.amount) DESC",
    )
    assert ascending.status_code == httpx.codes.OK
    assert descending.status_code == httpx.codes.OK
    ascending_numbers = [row["invoice_number"] for row in ascending.json()["invoices"]]
    descending_numbers = [row["invoice_number"] for row in descending.json()["invoices"]]
    assert ascending_numbers == list(reversed(descending_numbers))
    assert ascending_numbers != descending_numbers


def test_sort_injection_can_read_an_unrelated_table(vulnerable_client: httpx.Client) -> None:
    # The ORDER BY subquery touches integration_credentials; if that were unreachable this would
    # error instead of ordering. That it succeeds is the vulnerability.
    response = _list(vulnerable_client, supplier=BENIGN_SUPPLIER, sort=SORT_IDENTIFIER)
    assert response.status_code == httpx.codes.OK


def test_vulnerable_app_surfaces_the_query_it_built(vulnerable_client: httpx.Client) -> None:
    response = _list(vulnerable_client, supplier=TAUTOLOGY)
    statement = response.headers.get(EFFECTIVE_QUERY_HEADER)
    assert statement is not None
    # The payload appears inside the SQL as structure: data has become code, made legible.
    assert "OR '1'='1" in statement
    assert ":supplier" not in statement


def test_malformed_injection_returns_the_database_oracle(vulnerable_client: httpx.Client) -> None:
    # A broken injected identifier makes the database complain, and the vulnerable app hands that
    # complaint straight back — the very oracle the secure app withholds.
    response = _list(vulnerable_client, supplier=BENIGN_SUPPLIER, sort="not_a_real_column")
    assert response.status_code == httpx.codes.BAD_REQUEST
    assert "not_a_real_column" in response.text


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic nope"},
        {"Authorization": "Bearer demo-token-does-not-exist"},
    ],
)
def test_vulnerable_app_shares_the_generic_401(
    vulnerable_client: httpx.Client, headers: dict[str, str]
) -> None:
    response = vulnerable_client.get(
        "/invoices", params={"supplier": BENIGN_SUPPLIER}, headers=headers
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
