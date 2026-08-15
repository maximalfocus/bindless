"""The comparison engine.

Runs both applications through the same payloads and records, per payload, what each one did: the
query the vulnerable app assembled, how many rows came back, whether cross-tenant invoices or
credential rows leaked, and how the sort behaved. Every observation is made over real HTTP.

Like `scenarios.py`, this is plain functions over `httpx.Client` objects, so the whole comparison
can be built and asserted on from tests without any terminal involved. Rendering lives in `cli.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from bindless import fixtures
from bindless.api import EFFECTIVE_QUERY_HEADER
from bindless.payloads import TAUTOLOGY, UNION_CREDENTIALS
from bindless.scenarios import (
    HttpExchange,
    exchange_of,
    find_credentials,
    find_cross_tenant,
    json_body,
    rows_of,
)

__all__ = [
    "Comparison",
    "ComparisonRow",
    "Side",
    "run_comparison",
]

#: A sort payload whose ORDER BY reads the never-queried credentials table. Read-only.
SORT_INJECTION = "(SELECT api_key FROM integration_credentials LIMIT 1)"

#: The equivalent benign order for the secure app's allowlist, matching the vulnerable raw ORDER BY.
BENIGN_SECURE_SORT = "amount"
BENIGN_VULNERABLE_SORT = "i.amount DESC, i.invoice_number ASC"


@dataclass(frozen=True, slots=True)
class Side:
    """What one application did with one payload."""

    status_code: int
    row_count: int
    cross_tenant: tuple[str, ...]
    credentials: tuple[str, ...]
    effective_query: str | None
    invoices: tuple[dict[str, object], ...]
    exchange: HttpExchange

    @property
    def leaked(self) -> bool:
        return bool(self.cross_tenant) or bool(self.credentials)


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    key: str
    title: str
    attempt: str
    vulnerable: Side
    secure: Side
    #: True when the vulnerable app did the bad thing this payload is meant to trigger.
    exploit_expected: bool
    #: For a benign row, the two apps must agree; recorded so the CLI can show parity explicitly.
    parity: bool | None = None

    @property
    def secure_held(self) -> bool:
        """The secure app neither leaked nor produced a structural error oracle."""
        if self.secure.leaked:
            return False
        # A benign row should succeed; an attack row should be empty or cleanly refused.
        if self.exploit_expected:
            return self.secure.status_code in (httpx.codes.OK, httpx.codes.BAD_REQUEST)
        return self.secure.status_code == httpx.codes.OK

    @property
    def vulnerable_exploited(self) -> bool:
        if not self.exploit_expected:
            return False
        if self.secure is self.vulnerable:  # pragma: no cover - defensive
            return False
        # Either data leaked, or the injected identifier was accepted where the secure app refused.
        return self.vulnerable.leaked or (
            self.vulnerable.status_code == httpx.codes.OK
            and self.secure.status_code == httpx.codes.BAD_REQUEST
        )


@dataclass(frozen=True, slots=True)
class Comparison:
    rows: tuple[ComparisonRow, ...] = field(default_factory=tuple)

    @property
    def secure_holds_everywhere(self) -> bool:
        return all(row.secure_held for row in self.rows)

    @property
    def every_exploit_reproduced(self) -> bool:
        return all(row.vulnerable_exploited for row in self.rows if row.exploit_expected)

    @property
    def verdict_ok(self) -> bool:
        return self.secure_holds_everywhere and self.every_exploit_reproduced


def _authorized(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _observe(
    client: httpx.Client,
    *,
    supplier: str,
    sort: str | None,
    token: str,
    actor_org_id: int,
) -> Side:
    params: dict[str, str] = {"supplier": supplier}
    if sort is not None:
        params["sort"] = sort
    response = client.get("/invoices", params=params, headers=_authorized(token))
    payload = json_body(response)
    return Side(
        status_code=response.status_code,
        row_count=len(rows_of(payload)),
        cross_tenant=find_cross_tenant(payload, actor_org_id),
        credentials=find_credentials(payload),
        effective_query=response.headers.get(EFFECTIVE_QUERY_HEADER),
        invoices=tuple(rows_of(payload)),
        exchange=exchange_of(response),
    )


def compare_supplier_payload(
    secure_client: httpx.Client,
    vulnerable_client: httpx.Client,
    *,
    key: str,
    title: str,
    attempt: str,
    supplier: str,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    actor_org_id: int = 1,
    exploit_expected: bool = True,
) -> ComparisonRow:
    vulnerable = _observe(
        vulnerable_client,
        supplier=supplier,
        sort=None,
        token=token,
        actor_org_id=actor_org_id,
    )
    secure = _observe(
        secure_client, supplier=supplier, sort=None, token=token, actor_org_id=actor_org_id
    )
    return ComparisonRow(
        key=key,
        title=title,
        attempt=attempt,
        vulnerable=vulnerable,
        secure=secure,
        exploit_expected=exploit_expected,
    )


def compare_sort_injection(
    secure_client: httpx.Client,
    vulnerable_client: httpx.Client,
    *,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    actor_org_id: int = 1,
) -> ComparisonRow:
    vulnerable = _observe(
        vulnerable_client,
        supplier=fixtures.DEMO_BENIGN_SUPPLIER,
        sort=SORT_INJECTION,
        token=token,
        actor_org_id=actor_org_id,
    )
    secure = _observe(
        secure_client,
        supplier=fixtures.DEMO_BENIGN_SUPPLIER,
        sort=SORT_INJECTION,
        token=token,
        actor_org_id=actor_org_id,
    )
    return ComparisonRow(
        key="sort-injection",
        title="Injected ORDER BY identifier",
        attempt="sort=<subquery reading integration_credentials>",
        vulnerable=vulnerable,
        secure=secure,
        exploit_expected=True,
    )


def compare_benign(
    secure_client: httpx.Client,
    vulnerable_client: httpx.Client,
    *,
    token: str = fixtures.DEMO_ACTOR_TOKEN,
    actor_org_id: int = 1,
) -> ComparisonRow:
    vulnerable = _observe(
        vulnerable_client,
        supplier=fixtures.DEMO_BENIGN_SUPPLIER,
        sort=BENIGN_VULNERABLE_SORT,
        token=token,
        actor_org_id=actor_org_id,
    )
    secure = _observe(
        secure_client,
        supplier=fixtures.DEMO_BENIGN_SUPPLIER,
        sort=BENIGN_SECURE_SORT,
        token=token,
        actor_org_id=actor_org_id,
    )
    # The full bodies differ only in the echoed `sort` field (allowlist key vs raw ORDER BY); the
    # rows themselves — the legitimate result — must be identical.
    parity = (
        vulnerable.status_code == httpx.codes.OK
        and secure.status_code == httpx.codes.OK
        and vulnerable.invoices == secure.invoices
    )
    return ComparisonRow(
        key="benign",
        title="Benign search, legitimate sort",
        attempt=f"supplier={fixtures.DEMO_BENIGN_SUPPLIER!r}",
        vulnerable=vulnerable,
        secure=secure,
        exploit_expected=False,
        parity=parity,
    )


def run_comparison(
    secure_client: httpx.Client,
    vulnerable_client: httpx.Client,
    *,
    actor_org_id: int = 1,
) -> Comparison:
    """The full side-by-side comparison, in narrative order."""
    return Comparison(
        rows=(
            compare_benign(secure_client, vulnerable_client, actor_org_id=actor_org_id),
            compare_supplier_payload(
                secure_client,
                vulnerable_client,
                key="tautology",
                title="Tautology tenant-isolation break",
                attempt=f"supplier={TAUTOLOGY!r}",
                supplier=TAUTOLOGY,
                actor_org_id=actor_org_id,
            ),
            compare_supplier_payload(
                secure_client,
                vulnerable_client,
                key="union",
                title="UNION credential exfiltration",
                attempt="supplier=' UNION SELECT … FROM integration_credentials --",
                supplier=UNION_CREDENTIALS,
                actor_org_id=actor_org_id,
            ),
            compare_sort_injection(secure_client, vulnerable_client, actor_org_id=actor_org_id),
        )
    )
