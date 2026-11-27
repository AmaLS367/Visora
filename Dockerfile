# syntax=docker/dockerfile:1.7

# Pin both the immutable digest and the human-readable release tag. Dependabot
# maintains these references, preserving reproducible and reviewable updates.
FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM python:3.15.2-slim-bookworm@sha256:498829c717b1e59fc42f0e7865eafe4e04ca0f70a3769d4ae70ba218df54507c AS python

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
COPY README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

FROM python AS runtime

ARG APP_UID=10001
ARG APP_GID=10001
ARG VERSION=0.1.3

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
