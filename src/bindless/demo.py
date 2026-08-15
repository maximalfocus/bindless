"""The demonstration command.

Renders the walkthrough as a short narrative plus a result table, and ends in an explicit verdict.
Everything it reports was observed over real HTTP against the running application.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

import httpx

from bindless import fixtures
from bindless.scenarios import ScenarioOutcome, run_secure_walkthrough, wait_for_health

DEFAULT_SECURE_URL = "http://api-secure:8000"

NARRATIVE = """\
bindless — secure invoice portal walkthrough

A fictional supplier-invoice portal serves several tenant organizations from one database. The
caller below is a legitimately authenticated user of one of them. Every request goes through the
real HTTP endpoint, against freshly seeded, entirely invented data.

This application binds its values as parameters and resolves its sort column through a fixed
allowlist, so caller input is always treated as data and never as query structure.
"""


def _column_widths(rows: Sequence[Sequence[str]]) -> list[int]:
    return [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]


def render_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    all_rows = [list(header), *[list(row) for row in rows]]
    widths = _column_widths(all_rows)
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(header, widths, strict=True)).rstrip(),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in rows
    )
    return "\n".join(lines)


def render_outcomes(outcomes: Sequence[ScenarioOutcome]) -> str:
    rows = [
        [
            "PASS" if outcome.passed else "FAIL",
            outcome.title,
            outcome.expectation,
            outcome.observed,
        ]
        for outcome in outcomes
    ]
    return render_table(("RESULT", "SCENARIO", "EXPECTED", "OBSERVED"), rows)


def render_exchange(outcome: ScenarioOutcome) -> str:
    exchange = outcome.exchange
    body = exchange.body if len(exchange.body) <= 2000 else f"{exchange.body[:2000]}…"
    return (
        f"\n--- {outcome.key} ---\n"
        f"{exchange.method} {exchange.url}\n"
        f"HTTP {exchange.status_code}\n"
        f"{body}\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bindless-demo",
        description="Run the bindless walkthrough against a locally running application.",
    )
    parser.add_argument(
        "--secure-url",
        default=os.environ.get("BINDLESS_SECURE_URL", DEFAULT_SECURE_URL),
        help="Base URL of the secure application.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Also print the underlying HTTP exchange for every scenario.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    actor = fixtures.USERS[0]
    organization = next(org for org in fixtures.ORGANIZATIONS if org.id == actor.org_id)

    print(NARRATIVE)
    print(f"  caller       : {actor.display_name} <{actor.email}>")
    print(f"  organization : {organization.name} (id {organization.id})")
    print(f"  searching for: {fixtures.DEMO_BENIGN_SUPPLIER}")
    print(f"  application  : {args.secure_url}\n")

    with httpx.Client(base_url=args.secure_url, timeout=10.0) as client:
        wait_for_health(client)
        outcomes = run_secure_walkthrough(client)

    print(render_outcomes(outcomes))

    if args.verbose:
        for outcome in outcomes:
            print(render_exchange(outcome))

    failed = [outcome for outcome in outcomes if not outcome.passed]
    print()
    if failed:
        print(
            f"VERDICT: FAIL — {len(failed)} scenario(s) did not hold: "
            f"{', '.join(o.key for o in failed)}"
        )
        return 1
    print(
        "VERDICT: SECURE — the caller saw only its own organization's invoices, the "
        "non-allowlisted sort was refused without naming a valid column, every authentication "
        "failure looked the same, and the data was unchanged afterwards."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
