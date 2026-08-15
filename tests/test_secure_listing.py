"""The secure listing keeps values as values and keeps tenants apart."""

from __future__ import annotations

import httpx
import pytest

from bindless import fixtures
from bindless.payloads import CREDENTIAL_MARKER, TAUTOLOGY, UNION_CREDENTIALS
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


def test_benign_search_returns_only_the_callers_invoices(secure_client: httpx.Client) -> None:
    response = _list(secure_client, supplier=BENIGN_SUPPLIER, sort="invoice_number")
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["organization"] == {"id": 1, "name": "Northwind Freight"}
    numbers = [row["invoice_number"] for row in payload["invoices"]]
    assert numbers == ["INV-1001", "INV-1002", "INV-1003"]
    assert set(numbers) <= own_invoice_numbers(1)


def test_identical_supplier_name_in_another_organization_stays_invisible(
    secure_client: httpx.Client,
) -> None:
    # Organization 2 has a supplier with exactly the same name; guessability is not the defence.
    response = _list(secure_client, supplier=BENIGN_SUPPLIER, sort="invoice_number")
    numbers = {row["invoice_number"] for row in response.json()["invoices"]}
    assert numbers.isdisjoint(own_invoice_numbers(2))
    assert numbers.isdisjoint(own_invoice_numbers(3))


@pytest.mark.parametrize(
    ("token", "org_id", "supplier", "expected"),
    [
        (
            fixtures.USERS[0].demo_token,
            1,
            "Kestrel Logistics",
            ["INV-1001", "INV-1002", "INV-1003"],
        ),
        (fixtures.USERS[0].demo_token, 1, "Ambervale Packaging", ["INV-1004"]),
        (fixtures.USERS[1].demo_token, 2, "Kestrel Logistics", ["INV-2001", "INV-2002"]),
        (fixtures.USERS[2].demo_token, 3, "Vantage Instruments", ["INV-3001", "INV-3002"]),
    ],
)
def test_every_organization_sees_exactly_its_own_rows(
    secure_client: httpx.Client,
    token: str,
    org_id: int,
    supplier: str,
    expected: list[str],
) -> None:
    response = _list(secure_client, supplier=supplier, token=token, sort="invoice_number")
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["organization"]["id"] == org_id
    assert [row["invoice_number"] for row in payload["invoices"]] == expected


def test_tautology_is_matched_as_a_literal_supplier_name(secure_client: httpx.Client) -> None:
    response = _list(secure_client, supplier=TAUTOLOGY)
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["count"] == 0
    assert payload["invoices"] == []
    assert payload["organization"]["id"] == 1


def test_union_payload_cannot_reach_the_credentials_table(secure_client: httpx.Client) -> None:
    response = _list(secure_client, supplier=UNION_CREDENTIALS)
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["count"] == 0
    assert find_credentials(payload) == ()
    assert CREDENTIAL_MARKER not in response.text


def test_unknown_supplier_returns_an_empty_list_not_an_error(secure_client: httpx.Client) -> None:
    # A miss and a hostile payload look the same: neither is an oracle for what exists.
    response = _list(secure_client, supplier="No Such Supplier")
    assert response.status_code == httpx.codes.OK
    assert response.json()["count"] == 0


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("invoice_number", ["INV-1001", "INV-1002", "INV-1003"]),
        ("amount", ["INV-1003", "INV-1001", "INV-1002"]),
        ("status", ["INV-1002", "INV-1003", "INV-1001"]),
        ("supplier", ["INV-1001", "INV-1002", "INV-1003"]),
    ],
)
def test_allowlisted_sorts_order_the_result(
    secure_client: httpx.Client, sort: str, expected: list[str]
) -> None:
    response = _list(secure_client, supplier=BENIGN_SUPPLIER, sort=sort)
    assert response.status_code == httpx.codes.OK
    payload = response.json()
    assert payload["sort"] == sort
    assert [row["invoice_number"] for row in payload["invoices"]] == expected


def test_amounts_are_returned_with_exact_precision(secure_client: httpx.Client) -> None:
    response = _list(secure_client, supplier=BENIGN_SUPPLIER, sort="invoice_number")
    amounts = [row["amount"] for row in response.json()["invoices"]]
    assert amounts == ["1250.00", "890.50", "4300.00"]
