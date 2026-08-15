"""The vulnerable application.

**Local educational software. Never deploy this, and never copy its query construction.**

It refuses to start unless the operator has taken two deliberate actions: enabled its Compose
profile *and* set `ALLOW_VULNERABLE_DEMO=true`. Neither alone is enough, so it cannot be brought up
by accident or by a default `docker compose up`.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from bindless.api import create_app
from bindless.vulnerable_listing import list_invoices_vulnerably

#: The second of the two opt-in actions. The first is enabling the Compose profile.
ACKNOWLEDGEMENT_VARIABLE = "ALLOW_VULNERABLE_DEMO"
REQUIRED_ACKNOWLEDGEMENT = "true"

DESCRIPTION = (
    "Fictional supplier-invoice portal with a deliberately vulnerable listing query, for local "
    "educational use only. The listing SQL is assembled by string interpolation, so caller input "
    "is treated as query structure. Do not deploy. All data is invented."
)


class VulnerableDemoNotAcknowledgedError(RuntimeError):
    """Raised when the vulnerable application is started without the explicit acknowledgement."""


def require_acknowledgement(environ: dict[str, str] | None = None) -> None:
    """Refuse to start unless the operator explicitly acknowledged what this application is."""
    source = environ if environ is not None else dict(os.environ)
    if source.get(ACKNOWLEDGEMENT_VARIABLE) != REQUIRED_ACKNOWLEDGEMENT:
        raise VulnerableDemoNotAcknowledgedError(
            f"refusing to start: set {ACKNOWLEDGEMENT_VARIABLE}={REQUIRED_ACKNOWLEDGEMENT} to run "
            "the intentionally vulnerable application"
        )


def build_app() -> FastAPI:
    require_acknowledgement()
    return create_app(
        title="bindless — vulnerable invoice portal (DO NOT DEPLOY)",
        description=DESCRIPTION,
        list_invoices=list_invoices_vulnerably,
        expose_statement=True,
    )


app: FastAPI = build_app()
