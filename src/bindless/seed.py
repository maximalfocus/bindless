"""Load the deterministic fictional fixtures into a fresh database.

This runs as a one-shot container command before the applications start. It is deliberately not
reachable over HTTP: no application endpoint can reset or mutate demonstration state.
"""

from __future__ import annotations

from sqlalchemy import Engine

from bindless import fixtures
from bindless.db import create_db_engine, create_session_factory, session_scope, wait_until_ready
from bindless.models import (
    Base,
    IntegrationCredential,
    Invoice,
    Organization,
    Supplier,
    User,
)


def reset_schema(engine: Engine) -> None:
    """Drop and recreate every table so each run starts from identical state."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def load_fixtures(engine: Engine) -> None:
    """Insert every fixture group in foreign-key order, flushing between groups.

    The explicit flush is what keeps the order deterministic: each group is fully written before
    the next one references it.
    """
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        groups: list[list[Base]] = [
            [Organization(id=org.id, name=org.name) for org in fixtures.ORGANIZATIONS],
            [
                User(
                    id=user.id,
                    org_id=user.org_id,
                    email=user.email,
                    display_name=user.display_name,
                    demo_token=user.demo_token,
                )
                for user in fixtures.USERS
            ],
            [
                Supplier(id=supplier.id, org_id=supplier.org_id, name=supplier.name)
                for supplier in fixtures.SUPPLIERS
            ],
            [
                Invoice(
                    id=invoice.id,
                    org_id=invoice.org_id,
                    supplier_id=invoice.supplier_id,
                    invoice_number=invoice.invoice_number,
                    amount=invoice.amount,
                    status=invoice.status,
                )
                for invoice in fixtures.INVOICES
            ],
            [
                IntegrationCredential(
                    id=credential.id,
                    org_id=credential.org_id,
                    provider=credential.provider,
                    api_key=credential.api_key,
                    rotated_on=credential.rotated_on,
                )
                for credential in fixtures.INTEGRATION_CREDENTIALS
            ],
        ]
        for group in groups:
            session.add_all(group)
            session.flush()
        session.commit()


def seed() -> None:
    engine = create_db_engine()
    wait_until_ready(engine)
    reset_schema(engine)
    load_fixtures(engine)
    engine.dispose()


def main() -> None:
    seed()
    print(
        f"seeded {len(fixtures.ORGANIZATIONS)} organizations, "
        f"{len(fixtures.USERS)} users, "
        f"{len(fixtures.SUPPLIERS)} suppliers, "
        f"{len(fixtures.INVOICES)} invoices, "
        f"{len(fixtures.INTEGRATION_CREDENTIALS)} integration credentials"
    )


if __name__ == "__main__":
    main()
