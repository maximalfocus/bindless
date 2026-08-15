"""Demo-only bearer authentication.

Static tokens are a demonstration convenience, never a pattern to copy. What matters here is that
every authentication failure — missing, malformed, or unknown — is answered identically, so the
response never becomes an oracle for which tokens or users exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from bindless.models import Organization, User

BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}
GENERIC_UNAUTHORIZED_DETAIL = "Unauthorized"


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated fictional user and the single organization they belong to."""

    user_id: int
    email: str
    display_name: str
    org_id: int
    org_name: str


def parse_bearer_token(authorization: str | None) -> str | None:
    """Return the token from an `Authorization` header, or None if it is absent or malformed."""
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def resolve_principal(session: Session, authorization: str | None) -> Principal | None:
    """Resolve the caller, or None for a missing, malformed, or unknown credential."""
    token = parse_bearer_token(authorization)
    if token is None:
        return None
    row = session.execute(
        select(User, Organization)
        .join(Organization, Organization.id == User.org_id)
        .where(User.demo_token == token)
    ).first()
    if row is None:
        return None
    user, organization = row
    return Principal(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        org_id=organization.id,
        org_name=organization.name,
    )
