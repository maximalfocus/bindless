"""Response models shared by every application variant.

Both applications return this exact shape so their legitimate results can be compared directly.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class OrganizationOut(BaseModel):
    id: int
    name: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str


class InvoiceOut(BaseModel):
    invoice_number: str
    supplier: str
    amount: Decimal
    status: str


class InvoiceListResponse(BaseModel):
    """The caller's identity, the order applied, and the rows the query returned."""

    organization: OrganizationOut
    user: UserOut
    sort: str
    count: int
    invoices: list[InvoiceOut]


class HealthResponse(BaseModel):
    status: str
