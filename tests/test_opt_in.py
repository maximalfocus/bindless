"""The vulnerable application will not start without both deliberate opt-in actions."""

from __future__ import annotations

import pytest

from bindless.vulnerable_app import (
    ACKNOWLEDGEMENT_VARIABLE,
    VulnerableDemoNotAcknowledgedError,
    require_acknowledgement,
)


def test_missing_acknowledgement_refuses_to_start() -> None:
    with pytest.raises(VulnerableDemoNotAcknowledgedError):
        require_acknowledgement({})


@pytest.mark.parametrize("value", ["", "false", "1", "yes", "TRUE", "True"])
def test_only_the_exact_acknowledgement_is_accepted(value: str) -> None:
    with pytest.raises(VulnerableDemoNotAcknowledgedError):
        require_acknowledgement({ACKNOWLEDGEMENT_VARIABLE: value})


def test_the_exact_acknowledgement_permits_startup() -> None:
    # Does not raise.
    require_acknowledgement({ACKNOWLEDGEMENT_VARIABLE: "true"})
