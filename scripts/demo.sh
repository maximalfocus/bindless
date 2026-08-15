#!/usr/bin/env sh
# One-shot disposable demonstration: fresh database, deterministic fixtures, then the vulnerable and
# secure applications compared side by side over real HTTP, ending in a verdict. Requires Docker
# Compose and nothing else.
#
# The comparison needs the intentionally vulnerable application, so this is one of the deliberate
# opt-in contexts: it enables the `vulnerable` profile and sets the acknowledgement. Neither happens
# on the default `docker compose up` path.
set -eu

cd "$(dirname "$0")/.."

ALLOW_VULNERABLE_DEMO=true
export ALLOW_VULNERABLE_DEMO

PROFILES="--profile demo --profile vulnerable"

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
docker compose $PROFILES run --rm demo
status=$?
set -e
exit "$status"
