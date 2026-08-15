"""The rejection audit event: emitted exactly once, and leaking nothing."""

from __future__ import annotations

import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from bindless import fixtures
from bindless.api import REQUEST_ID_HEADER, create_app
from bindless.audit import EVENT_NAME, SortRejection, build_event, emit_sort_rejection
from bindless.listing import list_invoices_securely
from bindless.payloads import CREDENTIAL_MARKER, SORT_IDENTIFIER

REJECTION = SortRejection(request_id="req-123", user_id=1, org_id=1)


def test_event_has_the_required_fields() -> None:
    event = build_event(REJECTION)
    assert event["event"] == EVENT_NAME
    assert event["request_id"] == "req-123"
    assert event["actor_user_id"] == 1
    assert event["actor_org_id"] == 1
    assert event["action"] == "list_invoices"
    assert event["outcome"] == "rejected"
    assert "timestamp" in event


def test_event_never_carries_a_payload_token_or_identifier() -> None:
    serialized = json.dumps(build_event(REJECTION))
    for forbidden in (SORT_IDENTIFIER, "api_key", "invoice_number", CREDENTIAL_MARKER):
        assert forbidden not in serialized
    for user in fixtures.USERS:
        assert user.demo_token not in serialized


def test_emit_writes_exactly_one_json_line() -> None:
    stream = io.StringIO()
    emit_sort_rejection(REJECTION, stream=stream)
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == EVENT_NAME


def _capturing_app(events: list[SortRejection]) -> TestClient:
    app = create_app(
        title="test",
        description="test",
        list_invoices=list_invoices_securely,
        audit=events.append,
    )
    return TestClient(app)


def test_exactly_one_event_is_emitted_when_a_sort_is_rejected() -> None:
    events: list[SortRejection] = []
    with _capturing_app(events) as client:
        response = client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": SORT_IDENTIFIER},
            headers={"Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}"},
        )
    assert response.status_code == httpx.codes.BAD_REQUEST
    assert len(events) == 1
    assert events[0].org_id == 1
    assert events[0].user_id == 1


def test_no_event_is_emitted_when_the_sort_is_accepted() -> None:
    events: list[SortRejection] = []
    with _capturing_app(events) as client:
        response = client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": "amount"},
            headers={"Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}"},
        )
    assert response.status_code == httpx.codes.OK
    assert events == []


def test_no_event_is_emitted_when_authentication_fails() -> None:
    events: list[SortRejection] = []
    with _capturing_app(events) as client:
        response = client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": SORT_IDENTIFIER},
        )
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert events == []


def test_a_caller_supplied_request_id_is_used_for_correlation() -> None:
    captured: list[str] = []

    def capture(rejection: SortRejection) -> None:
        captured.append(rejection.request_id)

    app = create_app(
        title="test",
        description="test",
        list_invoices=list_invoices_securely,
        audit=capture,
    )
    with TestClient(app) as client:
        client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": SORT_IDENTIFIER},
            headers={
                "Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}",
                REQUEST_ID_HEADER: "correlation-xyz",
            },
        )
    assert captured == ["correlation-xyz"]


@pytest.mark.parametrize("sort", ["api_key", "1", "amount; DROP", "(SELECT 1)"])
def test_every_rejected_sort_emits_a_single_generic_event(sort: str) -> None:
    events: list[SortRejection] = []
    with _capturing_app(events) as client:
        client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER, "sort": sort},
            headers={"Authorization": f"Bearer {fixtures.DEMO_ACTOR_TOKEN}"},
        )
    assert len(events) == 1
