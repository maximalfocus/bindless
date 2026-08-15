"""Structural guarantees about how this project is allowed to run.

These assertions are about the shape of the project rather than a request/response: that the
database is not reachable from the host, that the API is loopback-only, that nothing logs
credentials, and that no vulnerable entry point exists yet.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

#: SQL that would change data. Only the one-shot seeder is allowed to contain any of it.
MUTATING_SQL = re.compile(r"\b(INSERT INTO|UPDATE |DELETE FROM|DROP TABLE|TRUNCATE|ALTER TABLE)")
SEEDER = "seed.py"


@pytest.fixture(scope="session")
def compose(repo_root: Path) -> dict[str, Any]:
    document = yaml.safe_load((repo_root / "compose.yaml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _services(compose: dict[str, Any]) -> dict[str, Any]:
    services = compose["services"]
    assert isinstance(services, dict)
    return services


def test_postgres_is_not_published_to_the_host(compose: dict[str, Any]) -> None:
    assert "ports" not in _services(compose)["db"]


@pytest.mark.parametrize("service", ["api-secure", "api-vulnerable"])
def test_the_apis_are_published_on_loopback_only(compose: dict[str, Any], service: str) -> None:
    published = _services(compose)[service].get("ports", [])
    assert published
    for mapping in published:
        assert str(mapping).startswith("127.0.0.1:"), mapping


@pytest.mark.parametrize("service", ["api-secure", "api-vulnerable"])
def test_the_apis_do_not_write_an_access_log(compose: dict[str, Any], service: str) -> None:
    # The access log would record query strings, and query strings carry the payloads.
    command = " ".join(str(part) for part in _services(compose)[service]["command"])
    assert "--no-access-log" in command


def test_the_secure_app_is_the_default_and_the_vulnerable_one_is_not(
    compose: dict[str, Any],
) -> None:
    # No profile on api-secure means the default `docker compose up` starts it.
    assert "profiles" not in _services(compose)["api-secure"]
    # The vulnerable app is gated behind a profile, so the default path never starts it.
    assert _services(compose)["api-vulnerable"]["profiles"] == ["vulnerable"]


def test_the_vulnerable_app_requires_the_acknowledgement_variable(compose: dict[str, Any]) -> None:
    environment = _services(compose)["api-vulnerable"]["environment"]
    assert "ALLOW_VULNERABLE_DEMO" in environment


def test_only_the_seeder_contains_mutating_sql(repo_root: Path) -> None:
    offenders: list[str] = []
    for path in sorted((repo_root / "src" / "bindless").glob("*.py")):
        if path.name == SEEDER:
            continue
        if MUTATING_SQL.search(path.read_text(encoding="utf-8")):
            offenders.append(path.name)
    assert offenders == []


def test_the_seeder_is_not_reachable_over_http(repo_root: Path) -> None:
    api = (repo_root / "src" / "bindless" / "api.py").read_text(encoding="utf-8")
    routes = re.findall(r'@app\.(get|post|put|patch|delete)\("([^"]+)"', api)
    assert {method for method, _ in routes} == {"get"}
    assert {path for _, path in routes} == {"/healthz", "/invoices"}
