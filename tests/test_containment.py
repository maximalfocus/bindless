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


def test_the_api_is_published_on_loopback_only(compose: dict[str, Any]) -> None:
    published = _services(compose)["api-secure"].get("ports", [])
    assert published
    for mapping in published:
        assert str(mapping).startswith("127.0.0.1:"), mapping


def test_the_api_does_not_write_an_access_log(compose: dict[str, Any]) -> None:
    # The access log would record query strings, and query strings carry the payloads.
    command = " ".join(str(part) for part in _services(compose)["api-secure"]["command"])
    assert "--no-access-log" in command


def test_no_vulnerable_service_exists_yet(compose: dict[str, Any]) -> None:
    assert [name for name in _services(compose) if "vulnerable" in name] == []


def test_no_vulnerable_entry_point_exists_yet(repo_root: Path) -> None:
    modules = {path.name for path in (repo_root / "src" / "bindless").glob("*.py")}
    assert "vulnerable_app.py" not in modules


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
