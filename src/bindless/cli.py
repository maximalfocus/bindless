"""The demonstration CLI.

Two modes, one engine:

* ``compare`` runs both applications through the scripted payloads and prints the side-by-side
  result — the effective query the vulnerable app built, the rows each returned, what leaked, the
  sort behaviour, and an explicit verdict. This is the default.
* ``interactive`` lets you type a supplier term and sort and watch the same comparison for your own
  input.

The engine lives in ``compare.py`` and is fully testable on its own; everything here is rendering
and argument handling.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

import httpx

from bindless import fixtures
from bindless.compare import (
    Comparison,
    ComparisonRow,
    Side,
    compare_supplier_payload,
    run_comparison,
)
from bindless.scenarios import wait_for_health

DEFAULT_SECURE_URL = "http://api-secure:8000"
DEFAULT_VULNERABLE_URL = "http://api-vulnerable:8000"

NARRATIVE = """\
bindless — the string that ran

A fictional supplier-invoice portal serves several tenant organizations from one database. Below,
one legitimately authenticated user of a single organization sends the same requests to two
versions of the same portal:

  vulnerable  builds its SQL by pasting your input into the query text
  secure      binds your input as parameters and allowlists the sort column

Every request goes through the real HTTP endpoint, against freshly seeded, entirely invented data.
Watch what changes — and what doesn't — between the two columns.
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


def describe_vulnerable(row: ComparisonRow) -> str:
    side = row.vulnerable
    if side.credentials:
        return f"{len(side.credentials)} credential value(s) exfiltrated"
    if side.cross_tenant:
        return f"{side.row_count} rows, {len(side.cross_tenant)} from other tenants"
    if row.key == "sort-injection" and side.status_code == httpx.codes.OK:
        return "injected ORDER BY accepted"
    if side.status_code >= httpx.codes.BAD_REQUEST:
        return f"HTTP {side.status_code}"
    return f"{side.row_count} rows, own tenant only"


def describe_secure(row: ComparisonRow) -> str:
    side = row.secure
    if side.status_code == httpx.codes.BAD_REQUEST:
        return "HTTP 400 — refused, no columns named"
    if side.leaked:  # pragma: no cover - would be a failing demonstration
        return f"LEAKED ({side.row_count} rows)"
    if row.exploit_expected:
        return f"{side.row_count} rows — filter held"
    return f"{side.row_count} rows, own tenant only"


def render_verdict_cell(row: ComparisonRow) -> str:
    if not row.exploit_expected:
        return "parity" if row.parity else "MISMATCH"
    if row.vulnerable_exploited and row.secure_held:
        return "vulnerable leaked · secure held"
    return "UNEXPECTED"


def render_comparison(comparison: Comparison) -> str:
    rows = [
        [
            row.title,
            describe_vulnerable(row),
            describe_secure(row),
            render_verdict_cell(row),
        ]
        for row in comparison.rows
    ]
    return render_table(("SCENARIO", "VULNERABLE APP", "SECURE APP", "VERDICT"), rows)


def render_effective_queries(comparison: Comparison) -> str:
    lines = ["Effective query the vulnerable app assembled (input shown as SQL structure):"]
    for row in comparison.rows:
        query = row.vulnerable.effective_query
        if query is None:
            continue
        lines.append(f"\n  {row.title}:")
        lines.append(f"    {query}")
    return "\n".join(lines)


def render_exchange(label: str, side: Side) -> str:
    exchange = side.exchange
    body = exchange.body if len(exchange.body) <= 2000 else f"{exchange.body[:2000]}…"
    query = f"\n  effective-query: {side.effective_query}" if side.effective_query else ""
    return (
        f"\n  [{label}] {exchange.method} {exchange.url}\n"
        f"  HTTP {exchange.status_code}{query}\n"
        f"  {body}"
    )


def render_verbose(comparison: Comparison) -> str:
    blocks = ["Underlying HTTP exchanges:"]
    for row in comparison.rows:
        blocks.append(f"\n--- {row.title} ---  ({row.attempt})")
        blocks.append(render_exchange("vulnerable", row.vulnerable))
        blocks.append(render_exchange("secure", row.secure))
    return "\n".join(blocks)


def render_header() -> str:
    actor = fixtures.USERS[0]
    organization = next(org for org in fixtures.ORGANIZATIONS if org.id == actor.org_id)
    return (
        f"{NARRATIVE}\n"
        f"  caller       : {actor.display_name} <{actor.email}>\n"
        f"  organization : {organization.name} (id {organization.id})\n"
    )


def _final_verdict(comparison: Comparison) -> tuple[str, int]:
    if comparison.verdict_ok:
        return (
            "VERDICT: the two applications diverge exactly where they should. Every payload that "
            "breaks tenant isolation, reads the credentials table, or injects the sort column "
            "succeeds against the vulnerable app and is neutralized by the secure one, while the "
            "legitimate request returns byte-identical rows from both.",
            0,
        )
    problems = [
        row.title
        for row in comparison.rows
        if not (row.secure_held and (row.parity or row.exploit_expected))
    ]
    return (f"VERDICT: FAIL — unexpected result for: {', '.join(problems)}", 1)


def _client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=10.0)


def run_compare(args: argparse.Namespace) -> int:
    print(render_header())
    with _client(args.secure_url) as secure, _client(args.vulnerable_url) as vulnerable:
        wait_for_health(secure)
        wait_for_health(vulnerable)
        comparison = run_comparison(secure, vulnerable)

    print(render_comparison(comparison))
    print()
    print(render_effective_queries(comparison))
    if args.verbose:
        print()
        print(render_verbose(comparison))
    message, code = _final_verdict(comparison)
    print()
    print(message)
    return code


def run_interactive(args: argparse.Namespace, *, input_fn: object = input) -> int:
    print(render_header())
    print("Enter a supplier term to compare the two apps. Blank line to quit.\n")
    reader = input_fn if callable(input_fn) else input
    with _client(args.secure_url) as secure, _client(args.vulnerable_url) as vulnerable:
        wait_for_health(secure)
        wait_for_health(vulnerable)
        while True:
            try:
                supplier = reader("supplier> ")
            except EOFError:
                break
            if not supplier:
                break
            row = compare_supplier_payload(
                secure,
                vulnerable,
                key="interactive",
                title=f"supplier={supplier!r}",
                attempt=f"supplier={supplier!r}",
                supplier=supplier,
                exploit_expected=False,
            )
            print(render_comparison(Comparison(rows=(row,))))
            if row.vulnerable.effective_query:
                print(f"  vulnerable query: {row.vulnerable.effective_query}")
            print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bindless",
        description="Compare the vulnerable and secure invoice portals side by side.",
    )
    parser.add_argument(
        "--secure-url",
        default=os.environ.get("BINDLESS_SECURE_URL", DEFAULT_SECURE_URL),
        help="Base URL of the secure application.",
    )
    parser.add_argument(
        "--vulnerable-url",
        default=os.environ.get("BINDLESS_VULNERABLE_URL", DEFAULT_VULNERABLE_URL),
        help="Base URL of the vulnerable application.",
    )
    subparsers = parser.add_subparsers(dest="mode")
    compare = subparsers.add_parser("compare", help="Run the scripted comparison (default).")
    compare.add_argument(
        "--verbose", action="store_true", help="Also print the underlying HTTP exchanges."
    )
    subparsers.add_parser("interactive", help="Type supplier terms and compare interactively.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Default to the scripted comparison when no subcommand is given.
    if args.mode == "interactive":
        return run_interactive(args)
    if not hasattr(args, "verbose"):
        args.verbose = False
    return run_compare(args)


if __name__ == "__main__":
    sys.exit(main())
