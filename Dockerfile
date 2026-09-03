# syntax=docker/dockerfile:1.7

# Pin both the immutable digest and the human-readable release tag. Dependabot
# maintains these references, preserving reproducible and reviewable updates.
FROM ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv

FROM python:3.10.19-slim-bookworm@sha256:23f63358922e79a794f71be8f3723c84e5ccca9638af3f74456dc73d6184499e AS python

FROM python AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# Keep third-party dependencies in a cacheable layer. The lockfile is enforced
# so image builds are deterministic with respect to Python dependencies.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-install-project

COPY backend ./backend
COPY README.md ./README.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python AS runtime

ARG APP_UID=10001
ARG APP_GID=10001
ARG VERSION=0.1.1

LABEL org.opencontainers.image.title="Visora" \
      org.opencontainers.image.description="High-level Model Context Protocol server for Unity Editor" \
      org.opencontainers.image.source="https://github.com/AmaLS367/Visora" \
      org.opencontainers.image.version="${VERSION}"

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASSET_CACHE_DIR=/data/cache

# Use stable IDs so mounted volumes can be given the correct ownership.
RUN groupadd --gid "${APP_GID}" visora \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --home-dir /home/visora \
        --shell /usr/sbin/nologin visora \
    && install --directory --owner=visora --group=visora --mode=0750 /data/cache

WORKDIR /app

# The final image contains only the immutable, non-editable application environment.
COPY --from=builder --chown=visora:visora /app/.venv /app/.venv

USER visora:visora

ENTRYPOINT ["visora"]
