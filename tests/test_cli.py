"""The CLI rendering and argument handling, and the interactive loop without a real terminal."""

from __future__ import annotations

import httpx

from bindless import cli, fixtures
from bindless.compare import Comparison, run_comparison
from bindless.payloads import CREDENTIAL_MARKER


def test_render_table_aligns_columns() -> None:
    rendered = cli.render_table(("A", "BB"), [["1", "2"], ["333", "4"]])
    lines = rendered.splitlines()
    assert lines[0].startswith("A")
    assert set(lines[1]) == {"-", " "}
    assert "333" in lines[3]


def test_render_comparison_reports_pass_verdicts(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    comparison = run_comparison(secure_client, vulnerable_client)
    rendered = cli.render_comparison(comparison)
    assert "SCENARIO" in rendered
    assert "VULNERABLE APP" in rendered
    assert "SECURE APP" in rendered
    assert "MISMATCH" not in rendered
    assert "UNEXPECTED" not in rendered
    assert "parity" in rendered
    assert "vulnerable leaked · secure held" in rendered


def test_effective_query_section_shows_injected_structure(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    rendered = cli.render_effective_queries(run_comparison(secure_client, vulnerable_client))
    assert "OR '1'='1" in rendered
    assert "integration_credentials" in rendered


def test_default_output_never_shows_secret_values(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    # The vulnerable app leaks credentials in its response body, but the summary output reports the
    # leak as a count, not by printing the secrets. Only verbose mode shows raw exchanges.
    comparison = run_comparison(secure_client, vulnerable_client)
    summary = cli.render_comparison(comparison) + cli.render_effective_queries(comparison)
    assert CREDENTIAL_MARKER not in summary


def test_verbose_output_includes_the_http_exchanges(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    rendered = cli.render_verbose(run_comparison(secure_client, vulnerable_client))
    assert "HTTP 200" in rendered
    assert "[vulnerable]" in rendered
    assert "[secure]" in rendered


def test_header_names_the_caller_and_organization() -> None:
    header = cli.render_header()
    assert fixtures.USERS[0].display_name in header
    assert "vulnerable" in header
    assert "secure" in header


def test_final_verdict_is_success_for_a_good_comparison(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    comparison = run_comparison(secure_client, vulnerable_client)
    message, code = cli._final_verdict(comparison)
    assert code == 0
    assert "VERDICT" in message


def test_compare_mode_exits_zero(
    secure_client: httpx.Client,
    vulnerable_client: httpx.Client,
) -> None:
    code = cli.main(
        [
            "--secure-url",
            str(secure_client.base_url),
            "--vulnerable-url",
            str(vulnerable_client.base_url),
            "compare",
        ]
    )
    assert code == 0


def test_no_subcommand_defaults_to_compare(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    code = cli.main(
        [
            "--secure-url",
            str(secure_client.base_url),
            "--vulnerable-url",
            str(vulnerable_client.base_url),
        ]
    )
    assert code == 0


def test_interactive_loop_runs_without_a_terminal(
    secure_client: httpx.Client, vulnerable_client: httpx.Client
) -> None:
    # Feed two supplier terms and then a blank line to quit — no real stdin involved.
    scripted = iter([fixtures.DEMO_BENIGN_SUPPLIER, "' OR '1'='1", ""])

    def fake_input(_prompt: str) -> str:
        return next(scripted)

    args = cli.build_parser().parse_args(
        [
            "--secure-url",
            str(secure_client.base_url),
            "--vulnerable-url",
            str(vulnerable_client.base_url),
            "interactive",
        ]
    )
    code = cli.run_interactive(args, input_fn=fake_input)
    assert code == 0


def test_empty_comparison_renders_without_error() -> None:
    assert "SCENARIO" in cli.render_comparison(Comparison())
