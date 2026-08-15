"""Every authentication failure is answered the same way."""

from __future__ import annotations

import httpx
import pytest

from bindless import fixtures
from bindless.auth import parse_bearer_token

# Trailing-whitespace variants are covered by the parsing test below instead: an HTTP client will
# not put an illegal header value on the wire, so they cannot be exercised end to end.
FAILING_HEADERS: list[dict[str, str]] = [
    {},
    {"Authorization": ""},
    {"Authorization": "Bearer"},
    {"Authorization": "Basic demo-token-northwind"},
    {"Authorization": "demo-token-northwind"},
    {"Authorization": "Bearer demo-token-does-not-exist"},
]


@pytest.mark.parametrize("headers", FAILING_HEADERS)
def test_missing_malformed_and_unknown_credentials_return_generic_401(
    secure_client: httpx.Client, headers: dict[str, str]
) -> None:
    response = secure_client.get(
        "/invoices", params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER}, headers=headers
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Unauthorized"}


def test_all_authentication_failures_are_byte_identical(secure_client: httpx.Client) -> None:
    bodies = {
        secure_client.get(
            "/invoices", params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER}, headers=headers
        ).text
        for headers in FAILING_HEADERS
    }
    assert len(bodies) == 1


def test_failure_response_never_echoes_the_supplied_credential(
    secure_client: httpx.Client,
) -> None:
    response = secure_client.get(
        "/invoices",
        params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER},
        headers={"Authorization": "Bearer some-token-the-caller-guessed"},
    )
    assert "some-token-the-caller-guessed" not in response.text


def test_a_valid_token_identifies_exactly_one_organization(secure_client: httpx.Client) -> None:
    for user in fixtures.USERS:
        response = secure_client.get(
            "/invoices",
            params={"supplier": fixtures.DEMO_BENIGN_SUPPLIER},
            headers={"Authorization": f"Bearer {user.demo_token}"},
        )
        assert response.status_code == httpx.codes.OK
        payload = response.json()
        assert payload["organization"]["id"] == user.org_id
        assert payload["user"]["email"] == user.email


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("", None),
        ("Bearer", None),
        ("Bearer   ", None),
        ("Basic abc", None),
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("BEARER  abc  ", "abc"),
    ],
)
def test_bearer_parsing(header: str | None, expected: str | None) -> None:
    assert parse_bearer_token(header) == expected
