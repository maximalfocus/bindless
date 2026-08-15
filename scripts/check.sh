#!/usr/bin/env sh
# The verification boundary: Ruff, mypy, and pytest inside the container image, against a freshly
# seeded database and the running application. CI runs this exact script.
set -eu

cd "$(dirname "$0")/.."

cleanup() {
  docker compose --profile demo --profile checks down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cleanup
docker compose --profile checks build
set +e
docker compose --profile checks run --rm checks
status=$?
set -e
exit "$status"
