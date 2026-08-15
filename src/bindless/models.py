"""The fictional multi-tenant supplier-invoice model.

`integration_credentials` is deliberately part of the same database and is never queried by any
application endpoint. Its only purpose is to make "a table this screen should never be able to
reach" a real, observable thing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for every fictional domain table."""


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    # A static, unmistakably demo-only bearer token. Real systems must never store or compare
    # credentials like this; it exists so the walkthrough has a stable identity per organization.
    demo_token: Mapped[str] = mapped_column(String(120), unique=True)


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_suppliers_org_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(120))


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20))


class IntegrationCredential(Base):
    """Fictional third-party integration secrets that no endpoint legitimately queries."""

    __tablename__ = "integration_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    provider: Mapped[str] = mapped_column(String(60))
    api_key: Mapped[str] = mapped_column(String(120))
    rotated_on: Mapped[date] = mapped_column(Date)
