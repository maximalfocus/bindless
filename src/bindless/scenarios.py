"""The scenario engine.

Every scenario is a plain function over an `httpx.Client`, so the whole walkthrough can be driven
from tests without simulating terminal input. Scenarios observe the applications only through the
real HTTP boundary — never by inspecting the database.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from bindless import fixtures
from bindless.payloads import CREDENTIAL_MARKER, SORT_IDENTIFIER


@dataclass(frozen=True, slots=True)
class HttpExchange:
    method: str
    url: str
    status_code: int
    body: str


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    key: str
    title: str
    expectation: str
    observed: str
    passed: bool
    exchange: HttpExchange
    row_count: int | None = None
    cross_tenant: tuple[str, ...] = field(default_factory=tuple)
    credentials: tuple[str, ...] = field(default_factory=tuple)


def own_invoice_numbers(org_id: int) -> frozenset[str]:
    """Invoice numbers the given organization legitimately owns."""
    return frozenset(
        invoice.invoice_number for invoice in fixtures.INVOICES if invoice.org_id == org_id
    )


def expected_invoice_numbers(org_id: int, supplier_name: str) -> tuple[str, ...]:
    """Invoice numbers an organization legitimately has for a supplier name."""
    supplier_ids = {
        supplier.id
        for supplier in fixtures.SUPPLIERS
        if supplier.org_id == org_id and supplier.name == supplier_name
    }
    return tuple(
        sorted(
            invoice.invoice_number
            for invoice in fixtures.INVOICES
            if invoice.org_id == org_id and invoice.supplier_id in supplier_ids
        )
    )


def rows_of(payload: object) -> list[dict[str, Any]]:
    """The invoice rows in a response body, or an empty list if the shape is unexpected."""
    if not isinstance(payload, dict):
        return []
    invoices = payload.get("invoices")
    if not isinstance(invoices, list):
        return []
    return [row for row in invoices if isinstance(row, dict)]


def find_cross_tenant(payload: object, actor_org_id: int) -> tuple[str, ...]:
    """Invoice numbers in the response that do not belong to the caller's organization."""
    owned = own_invoice_numbers(actor_org_id)
    return tuple(
        str(row.get("invoice_number"))
        for row in rows_of(payload)
        if str(row.get("invoice_number")) not in owned
    )


def find_credentials(payload: object) -> tuple[str, ...]:
    """Values in the response that came from the never-queried credentials table."""
    found: list[str] = []
    for row in rows_of(payload):
        for value in row.values():
            if isinstance(value, str) and CREDENTIAL_MARKER in value:
                found.append(value)
    return tuple(found)


def exchange_of(response: httpx.Response) -> HttpExchange:
    """A compact, printable record of one HTTP round trip."""
    return HttpExchange(
        method=response.request.method,
        url=str(response.request.url),
        status_code=response.status_code,
        body=response.text,
    )


def json_body(response: httpx.Response) -> object:
    """The parsed JSON body, or None when the response is not JSON."""
    try:
        return response.json()
    except ValueError:  # pragma: no cover - defensive
        return None


def wait_for_health(
    client: httpx.Client, *, attempts: int = 60, delay_seconds: float = 0.5
) -> None:
    """Poll `/healthz` until the application answers, or raise the last failure."""
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            response = client.get("/healthz")
        except httpx.HTTPError as error:  # pragma: no cover - timing dependent
            last_error = error
        else:
            if response.status_code == httpx.codes.OK:
                return
            last_error = httpx.HTTPStatusError(
                f"unhealthy: {response.status_code}", request=response.request, response=response
            )
        time.sleep(delay_seconds)
    if last_error is not None:  # pragma: no cover - timing dependent
        raise last_error


def _authorized(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def scenario_legitimate_listing(
    client: httpx.Client,
    *,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    actor_org_id: int = 1,
    sort: str = "amount",
) -> ScenarioOutcome:
    """A benign search with an allowlisted sort returns only the caller's own invoices."""
    response = client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": sort},
        headers=_authorized(token),
    )
    payload = json_body(response)
    cross_tenant = find_cross_tenant(payload, actor_org_id)
    credentials = find_credentials(payload)
    rows = rows_of(payload)
    expected = expected_invoice_numbers(actor_org_id, fixtures.DEMO_BENIGN_SUPPLIER)
    returned = tuple(sorted(str(row.get("invoice_number")) for row in rows))
    passed = (
        response.status_code == httpx.codes.OK
        and returned == expected
        and not cross_tenant
        and not credentials
    )
    return ScenarioOutcome(
        key="legitimate-listing",
        title="Benign search, allowlisted sort",
        expectation=f"{len(expected)} invoices, all from the caller's organization",
        observed=f"{len(rows)} invoices, {len(cross_tenant)} cross-tenant, "
        f"{len(credentials)} credential values",
        passed=passed,
        exchange=exchange_of(response),
        row_count=len(rows),
        cross_tenant=cross_tenant,
        credentials=credentials,
    )


def scenario_default_sort(
    client: httpx.Client,
    *,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    actor_org_id: int = 1,
) -> ScenarioOutcome:
    """Omitting `sort` falls back to the safe default rather than to caller-supplied text."""
    response = client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER},
        headers=_authorized(token),
    )
    payload = json_body(response)
    applied = payload.get("sort") if isinstance(payload, dict) else None
    passed = response.status_code == httpx.codes.OK and applied == "invoice_number"
    return ScenarioOutcome(
        key="default-sort",
        title="No sort requested",
        expectation="the safe default order is applied",
        observed=f"sort={applied!r}",
        passed=passed,
        exchange=exchange_of(response),
        row_count=len(rows_of(payload)),
        cross_tenant=find_cross_tenant(payload, actor_org_id),
        credentials=find_credentials(payload),
    )


def scenario_rejected_sort(
    client: httpx.Client,
    *,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    payload_value: str = SORT_IDENTIFIER,
) -> ScenarioOutcome:
    """A sort identifier outside the allowlist is refused without naming the valid ones."""
    response = client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": payload_value},
        headers=_authorized(token),
    )
    body = response.text
    leaks_identifier = any(
        column in body for column in ("invoice_number", "amount", "status", "supplier")
    )
    passed = (
        response.status_code == httpx.codes.BAD_REQUEST
        and not leaks_identifier
        and CREDENTIAL_MARKER not in body
    )
    return ScenarioOutcome(
        key="rejected-sort",
        title="Sort identifier outside the allowlist",
        expectation="generic 400 that names no valid column",
        observed=f"HTTP {response.status_code}, "
        f"{'leaks a column name' if leaks_identifier else 'no column names disclosed'}",
        passed=passed,
        exchange=exchange_of(response),
    )


def scenario_authentication(client: httpx.Client) -> tuple[ScenarioOutcome, ...]:
    """Missing, malformed, and unknown credentials are answered identically."""
    cases: tuple[tuple[str, dict[str, str]], ...] = (
        ("missing", {}),
        ("malformed", {"Authorization": "Basic not-a-bearer-token"}),
        ("unknown", {"Authorization": "Bearer demo-token-does-not-exist"}),
    )
    outcomes: list[ScenarioOutcome] = []
    bodies: list[str] = []
    for label, headers in cases:
        response = client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER},
            headers=headers,
        )
        bodies.append(response.text)
        challenge = response.headers.get("www-authenticate", "")
        passed = response.status_code == httpx.codes.UNAUTHORIZED and challenge.startswith("Bearer")
        outcomes.append(
            ScenarioOutcome(
                key=f"auth-{label}",
                title=f"{label.capitalize()} credential",
                expectation="generic 401 with a bearer challenge",
                observed=f"HTTP {response.status_code}, WWW-Authenticate={challenge!r}",
                passed=passed,
                exchange=exchange_of(response),
            )
        )
    identical = len(set(bodies)) == 1
    outcomes.append(
        ScenarioOutcome(
            key="auth-indistinguishable",
            title="All three failures are indistinguishable",
            expectation="one identical response body",
            observed="identical" if identical else "responses differ",
            passed=identical,
            exchange=outcomes[-1].exchange,
        )
    )
    return tuple(outcomes)


def scenario_state_unchanged(
    client: httpx.Client,
    baseline: ScenarioOutcome,
    *,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    sort: str = "amount",
) -> ScenarioOutcome:
    """Re-running the baseline after every other scenario returns a byte-identical response."""
    response = client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": sort},
        headers=_authorized(token),
    )
    identical = response.text == baseline.exchange.body
    return ScenarioOutcome(
        key="state-unchanged",
        title="Domain state after every scenario",
        expectation="the baseline response is byte-for-byte identical",
        observed="identical" if identical else "changed",
        passed=identical,
        exchange=exchange_of(response),
        row_count=len(rows_of(json_body(response))),
    )


def run_secure_walkthrough(client: httpx.Client, *, actor_org_id: int = 1) -> list[ScenarioOutcome]:
    """The complete secure-and-legitimate walkthrough, in narrative order."""
    baseline = scenario_legitimate_listing(client, actor_org_id=actor_org_id)
    outcomes = [
        baseline,
        scenario_default_sort(client, actor_org_id=actor_org_id),
        scenario_rejected_sort(client),
        *scenario_authentication(client),
    ]
    outcomes.append(scenario_state_unchanged(client, baseline))
    return outcomes
