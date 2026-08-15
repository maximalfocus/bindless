#!/usr/bin/env sh
# The verification boundary: Ruff, mypy, and pytest inside the container image, against a freshly
# seeded database and both running applications. CI runs this exact script.
#
# The regression matrix has to prove what the vulnerable application really does, so this script is
# one of the deliberate contexts that starts it: it enables the `vulnerable` profile and sets the
# acknowledgement. Neither happens on the default `docker compose up` path.
set -eu

cd "$(dirname "$0")/.."

ALLOW_VULNERABLE_DEMO=true
export ALLOW_VULNERABLE_DEMO

PROFILES="--profile checks --profile vulnerable"

cleanup() {
  docker compose --profile demo --profile checks --profile vulnerable \
    down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cleanup
# shellcheck disable=SC2086
docker compose $PROFILES build
set +e
# shellcheck disable=SC2086
docker compose $PROFILES run --rm checks
status=$?
set -e
exit "$status"
