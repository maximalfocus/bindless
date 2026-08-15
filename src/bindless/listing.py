"""The invoice listing query.

This module holds the *secure* construction. Two different kinds of untrusted input arrive here and
they need two different defences:

* `supplier` is a **value**. It is bound as a parameter, so the database receives it as data and
  never as query structure — whatever the caller types is matched as a literal supplier name.
* `sort` names a **column**. A parameter placeholder cannot stand in for an identifier, so binding
  cannot help. It is resolved through a fixed allowlist instead, and anything else is refused.

`org_id` is also bound, which is what keeps one tenant's rows invisible to another.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Connection, text

#: Permitted `sort` values mapped to the exact `ORDER BY` fragment each one is allowed to produce.
#: Every fragment ends in a unique column so ordering is total and therefore deterministic.
SORT_ALLOWLIST: Mapping[str, str] = {
    "invoice_number": "i.invoice_number ASC",
    "amount": "i.amount DESC, i.invoice_number ASC",
    "status": "i.status ASC, i.invoice_number ASC",
    "supplier": "s.name ASC, i.invoice_number ASC",
}

#: Used when the caller does not ask for an order at all.
DEFAULT_SORT = "invoice_number"

#: The projection both applications return, so their legitimate results are directly comparable.
LISTING_PROJECTION = "i.invoice_number, s.name AS supplier, i.amount, i.status"


class UnknownSortError(ValueError):
    """Raised when `sort` is not in the allowlist.

    Deliberately carries no detail about which identifiers would have been accepted.
    """


@dataclass(frozen=True, slots=True)
class InvoiceRow:
    invoice_number: str
    supplier: str
    amount: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class ListingResult:
    rows: tuple[InvoiceRow, ...]
    sort: str


def resolve_sort(sort: str | None) -> str:
    """Return the allowlisted sort key, or raise `UnknownSortError`."""
    if sort is None or sort == "":
        return DEFAULT_SORT
    if sort not in SORT_ALLOWLIST:
        raise UnknownSortError
    return sort


#: The finished statement for each allowlisted sort, assembled once when this module is imported.
#: Nothing is assembled per request, so there is no point at which caller input could reach the
#: statement text: it arrives only through the `:org_id` and `:supplier` placeholders.
SECURE_STATEMENTS: Mapping[str, str] = {
    key: (
        # The suppression below is deliberate and applies only here: every interpolated fragment
        # is a module-level constant defined above, and the two caller-supplied values arrive as
        # placeholders rather than text.
        f"SELECT {LISTING_PROJECTION} "  # noqa: S608
        "FROM invoices AS i "
        "JOIN suppliers AS s ON s.id = i.supplier_id "
        "WHERE i.org_id = :org_id AND s.name = :supplier "
        f"ORDER BY {fragment}"
    )
    for key, fragment in SORT_ALLOWLIST.items()
}


def secure_statement(sort_key: str) -> str:
    """Return the parameterized statement for an already-allowlisted sort key."""
    try:
        return SECURE_STATEMENTS[sort_key]
    except KeyError:
        raise UnknownSortError from None


def list_invoices_securely(
    connection: Connection,
    *,
    org_id: int,
    supplier: str,
    sort: str | None,
) -> ListingResult:
    """Return the caller organization's matching invoices, using bound values throughout."""
    sort_key = resolve_sort(sort)
    result = connection.execute(
        text(secure_statement(sort_key)),
        {"org_id": org_id, "supplier": supplier},
    )
    rows = tuple(
        InvoiceRow(
            invoice_number=record.invoice_number,
            supplier=record.supplier,
            amount=record.amount,
            status=record.status,
        )
        for record in result
    )
    return ListingResult(rows=rows, sort=sort_key)
