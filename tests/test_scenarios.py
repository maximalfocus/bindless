"""The scenario engine is driven directly, with no terminal input involved."""

from __future__ import annotations

import httpx

from bindless import fixtures
from bindless.demo import render_outcomes
from bindless.scenarios import (
    find_credentials,
    own_invoice_numbers,
    run_secure_walkthrough,
    scenario_authentication,
    scenario_default_sort,
    scenario_legitimate_listing,
    scenario_rejected_sort,
    scenario_state_unchanged,
)


def test_every_secure_scenario_passes(secure_client: httpx.Client) -> None:
    outcomes = run_secure_walkthrough(secure_client)
    failed = [outcome.key for outcome in outcomes if not outcome.passed]
    assert failed == []


def test_the_walkthrough_covers_the_required_ground(secure_client: httpx.Client) -> None:
    keys = {outcome.key for outcome in run_secure_walkthrough(secure_client)}
    assert keys == {
        "legitimate-listing",
        "default-sort",
        "rejected-sort",
        "auth-missing",
        "auth-malformed",
        "auth-unknown",
        "auth-indistinguishable",
        "state-unchanged",
    }


def test_legitimate_listing_reports_no_leak(secure_client: httpx.Client) -> None:
    outcome = scenario_legitimate_listing(secure_client)
    assert outcome.passed
    assert outcome.row_count == 3
    assert outcome.cross_tenant == ()
    assert outcome.credentials == ()


def test_default_sort_scenario_uses_the_safe_default(secure_client: httpx.Client) -> None:
    assert scenario_default_sort(secure_client).passed


def test_rejected_sort_scenario_sees_a_generic_refusal(secure_client: httpx.Client) -> None:
    outcome = scenario_rejected_sort(secure_client)
    assert outcome.passed
    assert outcome.exchange.status_code == httpx.codes.BAD_REQUEST


def test_authentication_scenarios_all_pass(secure_client: httpx.Client) -> None:
    outcomes = scenario_authentication(secure_client)
    assert [outcome.passed for outcome in outcomes] == [True, True, True, True]


def test_state_unchanged_scenario_compares_against_the_baseline(
    secure_client: httpx.Client,
) -> None:
    baseline = scenario_legitimate_listing(secure_client)
    assert scenario_state_unchanged(secure_client, baseline).passed


def test_leak_detectors_recognise_what_they_are_looking_for() -> None:
    # The detectors must actually fire, or a green walkthrough would prove nothing.
    foreign = {"invoices": [{"invoice_number": "INV-2001"}]}
    assert find_credentials(
        {"invoices": [{"supplier": fixtures.INTEGRATION_CREDENTIALS[0].api_key}]}
    )
    assert "INV-2001" not in own_invoice_numbers(1)
    assert foreign["invoices"][0]["invoice_number"] in own_invoice_numbers(2)
    assert find_credentials({"invoices": [{"supplier": "Kestrel Logistics"}]}) == ()


def test_outcomes_render_as_a_readable_table(secure_client: httpx.Client) -> None:
    rendered = render_outcomes(run_secure_walkthrough(secure_client))
    assert "RESULT" in rendered
    assert "SCENARIO" in rendered
    assert "FAIL" not in rendered
