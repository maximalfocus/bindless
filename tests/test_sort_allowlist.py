"""A parameter placeholder cannot stand in for an identifier — so `sort` uses an allowlist."""

from __future__ import annotations

import httpx
import pytest

from bindless import fixtures
from bindless.listing import (
    DEFAULT_SORT,
    SORT_ALLOWLIST,
    UnknownSortError,
    resolve_sort,
    secure_statement,
)
from bindless.payloads import CREDENTIAL_MARKER, SORT_IDENTIFIER

REJECTED_SORTS = [
    SORT_IDENTIFIER,
    "invoice_number; SELECT 1",
    "amount --",
    "(SELECT 1)",
    "invoice_number ASC, api_key",
    "api_key",
    "INVOICE_NUMBER",
    "1",
]


def test_default_is_applied_when_no_sort_is_requested() -> None:
    assert resolve_sort(None) == DEFAULT_SORT
    assert resolve_sort("") == DEFAULT_SORT


@pytest.mark.parametrize("sort", sorted(SORT_ALLOWLIST))
def test_allowlisted_keys_resolve_to_themselves(sort: str) -> None:
    assert resolve_sort(sort) == sort


@pytest.mark.parametrize("sort", REJECTED_SORTS)
def test_everything_outside_the_allowlist_is_refused(sort: str) -> None:
    with pytest.raises(UnknownSortError):
        resolve_sort(sort)


def test_only_allowlist_constants_can_reach_the_order_by_clause() -> None:
    for key, fragment in SORT_ALLOWLIST.items():
        assert secure_statement(key).endswith(f"ORDER BY {fragment}")
    assert ":org_id" in secure_statement(DEFAULT_SORT)
    assert ":supplier" in secure_statement(DEFAULT_SORT)


@pytest.mark.parametrize("sort", REJECTED_SORTS)
def test_rejection_is_generic_and_names_no_valid_column(
    secure_client: httpx.Client, sort: str
) -> None:
    response = secure_client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": sort},
        headers={"Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}"},
    )
    assert response.status_code == httpx.codes.BAD_REQUEST
    assert response.json() == {"detail": "Invalid sort parameter."}
    body = response.text
    for column in SORT_ALLOWLIST:
        assert column not in body
    assert CREDENTIAL_MARKER not in body


def test_rejection_does_not_reveal_whether_the_supplier_exists(
    secure_client: httpx.Client,
) -> None:
    headers = {"Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}"}
    known = secure_client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": "api_key"},
        headers=headers,
    )
    unknown = secure_client.get(
        "/invoices",
        params={"supplier": "No Such Supplier", "sort": "api_key"},
        headers=headers,
    )
    assert known.status_code == unknown.status_code
    assert known.text == unknown.text


def test_rejection_outranks_nothing_and_still_requires_authentication(
    secure_client: httpx.Client,
) -> None:
    # An unauthenticated caller learns nothing about sort validation.
    response = secure_client.get(
        "/invoices", params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": "api_key"}
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED
