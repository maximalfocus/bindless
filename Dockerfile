# Everything this project needs lives in here: Python, uv, the dependencies, and the tools that
# verify it. The host only ever needs Docker.
FROM python:3.13-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first, so editing source does not invalidate the dependency layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev


# The image the applications run as: runtime dependencies only, unprivileged.
FROM base AS runtime

RUN useradd --create-home --uid 10001 bindless && chown -R bindless:bindless /app
USER bindless
CMD ["uvicorn", "bindless.secure_app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]


# The image verification runs as: adds the dev tools and the test suite.
FROM base AS dev

RUN uv sync --frozen
COPY tests ./tests
COPY compose.yaml ./
ENV MYPY_CACHE_DIR=/tmp/mypy_cache \
    RUFF_CACHE_DIR=/tmp/ruff_cache
RUN useradd --create-home --uid 10001 bindless && chown -R bindless:bindless /app
USER bindless
CMD ["pytest"]
