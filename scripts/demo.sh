#!/usr/bin/env sh
# One-shot disposable demonstration: fresh database, deterministic fixtures, the walkthrough over
# real HTTP, then cleanup. Requires Docker Compose and nothing else.
set -eu

cd "$(dirname "$0")/.."

cleanup() {
  docker compose --profile demo --profile checks down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cleanup
docker compose --profile demo build
set +e
docker compose --profile demo run --rm demo
status=$?
set -e
exit "$status"
