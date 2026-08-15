"""Deterministic fictional fixtures.

Every organization, person, supplier, invoice, token, and "secret" below is invented for this
demonstration. The `.example` domain is reserved by RFC 2606 precisely so it cannot belong to
anyone. The integration credentials are conspicuously fake strings and are not accepted, used, or
transmitted anywhere.

Ordering and identifiers are fixed so row counts and sort order are stable across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class OrganizationFixture:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class UserFixture:
    id: int
    org_id: int
    email: str
    display_name: str
    demo_token: str


@dataclass(frozen=True, slots=True)
class SupplierFixture:
    id: int
    org_id: int
    name: str


@dataclass(frozen=True, slots=True)
class InvoiceFixture:
    id: int
    org_id: int
    supplier_id: int
    invoice_number: str
    amount: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class CredentialFixture:
    id: int
    org_id: int
    provider: str
    api_key: str
    rotated_on: date


ORGANIZATIONS: tuple[OrganizationFixture, ...] = (
    OrganizationFixture(1, "Northwind Freight"),
    OrganizationFixture(2, "Harborline Textiles"),
    OrganizationFixture(3, "Solvent Analytics"),
)

USERS: tuple[UserFixture, ...] = (
    UserFixture(1, 1, "dana.reyes@northwind-freight.example", "Dana Reyes", "demo-token-northwind"),
    UserFixture(
        2, 2, "priya.okafor@harborline-textiles.example", "Priya Okafor", "demo-token-harborline"
    ),
    UserFixture(
        3, 3, "marc.lindqvist@solvent-analytics.example", "Marc Lindqvist", "demo-token-solvent"
    ),
)

SUPPLIERS: tuple[SupplierFixture, ...] = (
    SupplierFixture(1, 1, "Kestrel Logistics"),
    SupplierFixture(2, 1, "Ambervale Packaging"),
    # Deliberately the same supplier name under a different organization: even an identical,
    # perfectly guessable name must stay behind the tenant boundary.
    SupplierFixture(3, 2, "Kestrel Logistics"),
    SupplierFixture(4, 2, "Tidewater Print"),
    SupplierFixture(5, 3, "Vantage Instruments"),
)

INVOICES: tuple[InvoiceFixture, ...] = (
    InvoiceFixture(1, 1, 1, "INV-1001", Decimal("1250.00"), "paid"),
    InvoiceFixture(2, 1, 1, "INV-1002", Decimal("890.50"), "open"),
    InvoiceFixture(3, 1, 1, "INV-1003", Decimal("4300.00"), "open"),
    InvoiceFixture(4, 1, 2, "INV-1004", Decimal("275.25"), "paid"),
    InvoiceFixture(5, 2, 3, "INV-2001", Decimal("9900.00"), "open"),
    InvoiceFixture(6, 2, 3, "INV-2002", Decimal("150.75"), "paid"),
    InvoiceFixture(7, 2, 4, "INV-2003", Decimal("620.00"), "disputed"),
    InvoiceFixture(8, 3, 5, "INV-3001", Decimal("18750.00"), "open"),
    InvoiceFixture(9, 3, 5, "INV-3002", Decimal("42.10"), "paid"),
)

INTEGRATION_CREDENTIALS: tuple[CredentialFixture, ...] = (
    CredentialFixture(
        1, 1, "ledgerlink", "DEMO-FAKE-SECRET-ledgerlink-northwind-0001", date(2026, 1, 4)
    ),
    CredentialFixture(
        2, 2, "parcelgate", "DEMO-FAKE-SECRET-parcelgate-harborline-0002", date(2026, 2, 17)
    ),
    CredentialFixture(
        3, 3, "assaybridge", "DEMO-FAKE-SECRET-assaybridge-solvent-0003", date(2026, 3, 29)
    ),
)

#: The organization whose authenticated user drives the walkthrough.
DEMO_ACTOR_TOKEN = USERS[0].demo_token
#: A supplier name the demo actor legitimately has invoices for.
DEMO_BENIGN_SUPPLIER = SUPPLIERS[0].name
