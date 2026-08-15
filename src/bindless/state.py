"""A deterministic digest of the disposable domain state.

Used by the regression suite to prove that no request path — legitimate or hostile — changes a
single byte of the fixture data.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import Connection, text

#: Every table the fixtures populate, including the one no endpoint may reach.
DOMAIN_TABLES: tuple[str, ...] = (
    "organizations",
    "users",
    "suppliers",
    "invoices",
    "integration_credentials",
)


def domain_state_digest(connection: Connection) -> str:
    """Hash every fixture row, in a stable order, across every domain table."""
    hasher = hashlib.sha256()
    for table in DOMAIN_TABLES:
        hasher.update(f"table:{table}\n".encode())
        # `table` is one of the module-level constants above; no caller input reaches this string.
        rows = connection.execute(
            text(f"SELECT * FROM {table} ORDER BY id")  # noqa: S608 - fixed table allowlist
        ).mappings()
        for row in rows:
            hasher.update(repr(sorted((key, str(value)) for key, value in row.items())).encode())
            hasher.update(b"\n")
    return hasher.hexdigest()
