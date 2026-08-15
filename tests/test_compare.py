"""The comparison engine, driven directly against both running applications."""

from __future__ import annotations

import httpx

from bindless.compare import (
    Comparison,
    compare_benign,
    compare_sort_injection,
    compare_supplier_payload,
    run_comparison,
)
from bindless.payloads import TAUTOLOGY, UNION_CREDENTIALS


def test_full_comparison_verdict_is_ok(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    comparison = run_comparison(secure_client, vulnerable_client)
    assert comparison.verdict_ok
    assert comparison.secure_holds_everywhere
    assert comparison.every_exploit_reproduced


def test_comparison_covers_every_scenario(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    keys = {row.key for row in run_comparison(secure_client, vulnerable_client).rows}
    assert keys == {"benign", "tautology", "union", "sort-injection"}


def test_benign_row_shows_parity(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    row = compare_benign(secure_client, vulnerable_client)
    assert row.parity is True
    assert not row.exploit_expected
    assert row.secure_held
    assert row.vulnerable.invoices == row.secure.invoices
    assert row.vulnerable.invoices  # actually returned something


def test_tautology_row_contrast(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    row = compare_supplier_payload(
        secure_client,
        vulnerable_client,
        key="tautology",
        title="Tautology",
        attempt="supplier tautology",
        supplier=TAUTOLOGY,
    )
    assert row.vulnerable.cross_tenant  # other tenants' rows leaked
    assert row.vulnerable_exploited
    assert row.secure.row_count == 0
    assert row.secure_held


def test_union_row_contrast(secure_client: httpx.Client, vulnerable_client: httpx.Client) -> None:
    row = compare_supplier_payload(
        secure_client,
        vulnerable_client,
        key="union",
        title="UNION",
        attempt="union",
        supplier=UNION_CREDENTIALS,
    )
    assert row.vulnerable.credentials
    assert row.vulnerable_exploited
    assert row.secure.credentials == ()
    assert row.secure.row_count == 0
    assert row.secure_held


def test_sort_injection_row_contrast(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    row = compare_sort_injection(secure_client, vulnerable_client)
    assert row.vulnerable.status_code == httpx.codes.OK
    assert row.secure.status_code == httpx.codes.BAD_REQUEST
    assert row.vulnerable_exploited
    assert row.secure_held


def test_vulnerable_side_carries_the_effective_query(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    for row in run_comparison(secure_client, vulnerable_client).rows:
        assert row.vulnerable.effective_query is not None
        assert row.secure.effective_query is None  # the secure app never exposes its query


def test_empty_comparison_is_vacuously_ok() -> None:
    empty = Comparison()
    assert empty.verdict_ok
