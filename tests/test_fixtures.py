"""The fixtures are deterministic, and conspicuously fictional."""

from __future__ import annotations

from bindless import fixtures
from bindless.payloads import CREDENTIAL_MARKER


def test_identifiers_are_unique() -> None:
    for collection in (
        fixtures.ORGANIZATIONS,
        fixtures.USERS,
        fixtures.SUPPLIERS,
        fixtures.INVOICES,
        fixtures.INTEGRATION_CREDENTIALS,
    ):
        identifiers = [item.id for item in collection]
        assert len(identifiers) == len(set(identifiers))
        assert identifiers == sorted(identifiers)


def test_invoice_numbers_and_tokens_are_unique() -> None:
    numbers = [invoice.invoice_number for invoice in fixtures.INVOICES]
    tokens = [user.demo_token for user in fixtures.USERS]
    assert len(numbers) == len(set(numbers))
    assert len(tokens) == len(set(tokens))


def test_every_user_belongs_to_exactly_one_organization() -> None:
    org_ids = {org.id for org in fixtures.ORGANIZATIONS}
    assert all(user.org_id in org_ids for user in fixtures.USERS)
    assert len({user.org_id for user in fixtures.USERS}) == len(fixtures.USERS)


def test_invoices_reference_a_supplier_in_their_own_organization() -> None:
    suppliers = {supplier.id: supplier for supplier in fixtures.SUPPLIERS}
    for invoice in fixtures.INVOICES:
        assert suppliers[invoice.supplier_id].org_id == invoice.org_id


def test_more_than_one_organization_has_invoices() -> None:
    # Without this the tenant-isolation demonstration would have nothing to show.
    assert len({invoice.org_id for invoice in fixtures.INVOICES}) > 1


def test_a_supplier_name_is_shared_across_organizations() -> None:
    names = [supplier.name for supplier in fixtures.SUPPLIERS]
    assert any(names.count(name) > 1 for name in names)


def test_demo_identities_use_the_reserved_example_domain() -> None:
    assert all(user.email.endswith(".example") for user in fixtures.USERS)
    assert all(user.demo_token.startswith("demo-token-") for user in fixtures.USERS)


def test_demonstration_secrets_are_obviously_fake() -> None:
    assert fixtures.INTEGRATION_CREDENTIALS
    assert all(
        CREDENTIAL_MARKER in credential.api_key for credential in fixtures.INTEGRATION_CREDENTIALS
    )


def test_the_actor_has_invoices_for_the_benign_supplier() -> None:
    actor = fixtures.USERS[0]
    supplier_ids = {
        supplier.id
        for supplier in fixtures.SUPPLIERS
        if supplier.org_id == actor.org_id and supplier.name == fixtures.DEMO_BENIGN_SUPPLIER
    }
    matching = [
        invoice
        for invoice in fixtures.INVOICES
        if invoice.org_id == actor.org_id and invoice.supplier_id in supplier_ids
    ]
    assert len(matching) >= 2
