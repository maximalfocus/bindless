"""The secure application — the one that gets the query construction right.

Values (`org_id`, `supplier`) are bound as parameters. The `sort` identifier is resolved through a
fixed allowlist. There is no other difference in behaviour: same method, same path, same
authentication, same successful response.
"""

from __future__ import annotations

from fastapi import FastAPI

from bindless.api import create_app
from bindless.audit import emit_sort_rejection
from bindless.listing import list_invoices_securely

DESCRIPTION = (
    "Fictional supplier-invoice portal. Values are bound as parameters and the sort identifier is "
    "resolved through a fixed allowlist. Local educational software; all data is invented."
)

app: FastAPI = create_app(
    title="bindless — secure invoice portal",
    description=DESCRIPTION,
    list_invoices=list_invoices_securely,
    audit=emit_sort_rejection,
)
