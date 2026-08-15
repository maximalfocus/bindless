"""The rejection audit event.

When the secure application refuses a sort identifier, it says so once, to standard output, as one
structured JSON object.

What the event deliberately does *not* contain is as important as what it does: no bearer token, no
authorization header, no personal information, and no echo of the rejected value. Logging the
payload back would hand an attacker a confirmation channel and would put hostile text into the
place operators trust most.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TextIO

EVENT_NAME = "listing.sort_rejected"


@dataclass(frozen=True, slots=True)
class SortRejection:
    """Everything the event is allowed to know about a refused request."""

    request_id: str
    user_id: int
    org_id: int


def build_event(rejection: SortRejection) -> dict[str, object]:
    return {
        "event": EVENT_NAME,
        "request_id": rejection.request_id,
        "actor_user_id": rejection.user_id,
        "actor_org_id": rejection.org_id,
        "action": "list_invoices",
        "outcome": "rejected",
        "reason": "sort_not_allowlisted",
        "timestamp": datetime.now(UTC).isoformat(),
    }


def emit_sort_rejection(rejection: SortRejection, *, stream: TextIO | None = None) -> None:
    """Write exactly one JSON line describing the refusal."""
    print(
        json.dumps(build_event(rejection), sort_keys=True, separators=(",", ":")),
        file=stream if stream is not None else sys.stdout,
        flush=True,
    )
