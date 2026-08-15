"""The security regression matrix: the two applications, the same payloads, side by side.

Each test sends one payload to both applications and asserts the contrast the PRD requires — the
vulnerable app leaks, the secure app holds — so the fix is proven against the flaw, not in the
abstract.
"""

from __future__ import annotations

import httpx
import pytest

from bindless import fixtures
from bindless.payloads import CREDENTIAL_MARKER, TAUTOLOGY, UNION_CREDENTIALS
from bindless.scenarios import find_credentials, own_invoice_numbers

ACTOR_TOKEN = fixtures.DEMO_ACTOR_TOKEN
BENIGN_SUPPLIER = fixtures.DEMO_BENIGN_SUPPLIER


def _list(
    client: httpx.Client, *, supplier: str, sort: str | None = None, token: str = ACTOR_TOKEN
) -> httpx.Response:
    params: dict[str, str] = {"supplier": supplier}
    if sort is not None:
        params["sort"] = sort
    return client.get("/invoices", params=params, headers={"Authorization": f"Bearer {token}"})


def test_tautology_leaks_on_vulnerable_and_holds_on_secure(
    vulnerable_client: httpx.Client, secure_client: httpx.Client
) -> None:
    vulnerable = _list(vulnerable_client, supplier=TAUTOLOGY).json()
    secure = _list(secure_client, supplier=TAUTOLOGY).json()

    vulnerable_numbers = {row["invoice_number"] for row in vulnerable["invoices"]}
    assert vulnerable_numbers & own_invoice_numbers(2)  # other tenants' rows leak

    assert secure["count"] == 0  # the org_id filter holds
    assert secure["organization"]["id"] == 1


def test_union_leaks_credentials_on_vulnerable_and_holds_on_secure(
    vulnerable_client: httpx.Client, secure_client: httpx.Client
) -> None:
    vulnerable = _list(vulnerable_client, supplier=UNION_CREDENTIALS)
    secure = _list(secure_client, supplier=UNION_CREDENTIALS)

    assert find_credentials(vulnerable.json())  # the never-queried table is reached

    assert secure.json()["count"] == 0  # unreachable here
    assert find_credentials(secure.json()) == ()
    assert CREDENTIAL_MARKER not in secure.text


def test_sort_injection_reaches_order_by_on_vulnerable_and_is_refused_on_secure(
    vulnerable_client: httpx.Client, secure_client: httpx.Client
) -> None:
    injected = "(SELECT count(*) FROM invoices x WHERE x.amount <= i.amount) DESC"
    vulnerable = _list(vulnerable_client, supplier=BENIGN_SUPPLIER, sort=injected)
    secure = _list(secure_client, supplier=BENIGN_SUPPLIER, sort=injected)

    assert vulnerable.status_code == httpx.codes.OK  # the identifier reaches ORDER BY

    assert secure.status_code == httpx.codes.BAD_REQUEST  # refused by the allowlist
    assert secure.json() == {"detail": "Invalid sort parameter."}


def test_secure_app_reveals_no_structural_error_oracle(secure_client: httpx.Client) -> None:
    # A malformed identifier that makes the vulnerable app emit a database error must, on the
    # secure app, produce only the same generic refusal.
    response = _list(secure_client, supplier=BENIGN_SUPPLIER, sort="no_such_column")
    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {"detail": "Invalid sort parameter."}


def test_allowlisted_sort_succeeds_on_the_secure_app(secure_client: httpx.Client) -> None:
    response = _list(secure_client, supplier=BENIGN_SUPPLIER, sort="amount")
    assert response.status_code == httpx.codes.OK
    assert response.json()["sort"] == "amount"


@pytest.mark.parametrize(
    ("supplier", "sort", "expected"),
    [
        ("Kestrel Logistics", "amount", ["INV-1003", "INV-1001", "INV-1002"]),
        ("Kestrel Logistics", "invoice_number", ["INV-1001", "INV-1002", "INV-1003"]),
        ("Ambervale Packaging", "invoice_number", ["INV-1004"]),
    ],
)
def test_both_apps_agree_on_benign_input(
    vulnerable_client: httpx.Client,
    secure_client: httpx.Client,
    supplier: str,
    sort: str,
    expected: list[str],
) -> None:
    # The secure app takes an allowlist key; the vulnerable app takes a raw ORDER BY. For a benign
    # request the observable result is identical: the same rows, in the same requested order.
    secure = _list(secure_client, supplier=supplier, sort=sort)
    raw_order = {
        "amount": "i.amount DESC, i.invoice_number ASC",
        "invoice_number": "i.invoice_number ASC",
    }[sort]
    vulnerable = _list(vulnerable_client, supplier=supplier, sort=raw_order)

    assert secure.status_code == httpx.codes.OK
    assert vulnerable.status_code == httpx.codes.OK
    assert secure.json()["invoices"] == vulnerable.json()["invoices"]
    assert [row["invoice_number"] for row in secure.json()["invoices"]] == expected


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic nope"},
        {"Authorization": "Bearer demo-token-does-not-exist"},
    ],
)
def test_both_apps_share_generic_401(
    vulnerable_client: httpx.Client,
    secure_client: httpx.Client,
    headers: dict[str, str],
) -> None:
    for client in (vulnerable_client, secure_client):
        response = client.get("/invoices", params={"supplier": BENIGN_SUPPLIER}, headers=headers)
        assert response.status_code == httpx.codes.UNAUTHORIZED
        assert response.headers["www-authenticate"] == "Bearer"
