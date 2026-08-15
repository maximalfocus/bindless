"""The vulnerable listing query — the flaw this project exists to demonstrate.

**This code is deliberately wrong. Do not copy it.**

Every part of the statement below is assembled by pasting caller-controlled text straight into SQL:
the tenant filter, the supplier term, and the sort column. The database therefore receives the
caller's input as *query structure*, not as data, and there is no longer any difference between
"what the user typed" and "what the query says".

Compare with `listing.py`, which is the same query written correctly. The observable contract —
method, path, authentication, successful response shape — is identical. The only difference is how
the statement is built, and that difference is the entire lesson.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from sqlalchemy import Connection
from sqlalchemy.engine import Row

from bindless.listing import LISTING_PROJECTION, InvoiceRow, ListingResult

#: What the vulnerable application orders by when the caller asks for nothing. Unlike the secure
#: application this is only a default, not a constraint: any caller-supplied text replaces it.
DEFAULT_ORDER_BY = "i.invoice_number ASC"


def vulnerable_statement(org_id: int, supplier: str, sort: str | None) -> str:
    """Assemble the listing SQL by string interpolation, exactly as the flaw requires.

    Note what is missing: no placeholders, no escaping, no allowlist. `org_id` is interpolated too,
    which is why a tautology in `supplier` can dissolve the tenant boundary — `AND` binds tighter
    than `OR`, so `org_id = 1 AND name = '' OR '1'='1'` is true for every row in the table.
    """
    order_by = sort if sort else DEFAULT_ORDER_BY
    # The linter is right, and that is the whole point: this is the vulnerability under glass.
    return (
        f"SELECT {LISTING_PROJECTION} "  # noqa: S608
        "FROM invoices AS i "
        "JOIN suppliers AS s ON s.id = i.supplier_id "
        f"WHERE i.org_id = {org_id} AND s.name = '{supplier}' "
        f"ORDER BY {order_by}"
    )


def _row(record: Row[tuple[object, ...]]) -> InvoiceRow:
    # An injected UNION can put anything at all in these positions, so nothing is assumed about the
    # values beyond their column order. `amount` is whatever the injected column yielded; it is
    # carried through as-is and only serialized for display.
    invoice_number, supplier, amount, status = record
    return InvoiceRow(
        invoice_number=str(invoice_number),
        supplier=str(supplier),
        amount=cast(Decimal, amount),
        status=str(status),
    )


def list_invoices_vulnerably(
    connection: Connection,
    *,
    org_id: int,
    supplier: str,
    sort: str | None,
) -> ListingResult:
    """Run the string-built statement and return whatever the database hands back."""
    statement = vulnerable_statement(org_id, supplier, sort)
    # Sent to the driver as a finished string with no parameters — there is nothing left to bind.
    result = connection.exec_driver_sql(statement)
    rows = tuple(_row(record) for record in result)
    return ListingResult(rows=rows, sort=sort or "invoice_number", statement=statement)
