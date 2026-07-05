# syntax=docker/dockerfile:1
#
# MintMory REST API container image (MM-43).
#
# Packaging only — no application changes. The image runs the FastAPI app with a
# single uvicorn worker (the SQLite store is single-writer; more than one worker
# or replica would corrupt the WAL) and no --reload (that is the dev entrypoint).
#
#   VARIANT=light (default) -> [otel] extra: hashing embedder + OpenTelemetry, no
#                              torch. ~700 MB. Fully functional (heavy extras are
#                              lazy-imported and degrade gracefully).
#   VARIANT=full            -> also [local] extra: sentence-transformers + torch
#                              (~2 GB). Only build this if you need local embeddings.
#
# Build:
#   docker build --build-arg VARIANT=light -t mintmory:light .
#   docker build --build-arg VARIANT=full  -t mintmory:full  .
#
# NOTE on the sync command: the `otel` / `local` extras are declared on the
# mintmory-core workspace member, not on mintmory-api. `uv sync --frozen --extra
# otel` therefore syncs the whole uv workspace (which installs mintmory-api plus
# its transitive deps) with the requested extra. `--no-dev` drops pytest/ruff/mypy.
# `--frozen` installs strictly from the committed uv.lock and fails if the lock has
# drifted from pyproject.toml — a supply-chain guard for reproducible builds.
FROM python:3.12-slim AS base

ARG VARIANT=light
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy what uv needs to resolve + install the workspace. uv.lock is committed to
# the repo (MM-44), so it is in the build context on every checkout — we install
# from it with `--frozen` for reproducible, pinned images, consistent with how the
# CI `gates` job syncs. `--frozen` fails the build if the lock drifts from
# pyproject.toml (regenerate with `uv lock` and commit).
COPY pyproject.toml uv.lock ./
COPY packages ./packages

RUN if [ "$VARIANT" = "full" ]; then \
        uv sync --frozen --no-dev --extra otel --extra local ; \
    else \
        uv sync --frozen --no-dev --extra otel ; \
    fi

# Non-root runtime user; writable data volume for the SQLite store (+ WAL/SHM).
RUN useradd -u 10001 -m app \
    && mkdir -p /data \
    && chown -R app:app /data /app
USER app

VOLUME ["/data"]

ENV MINTMORY_DB=/data/memories.db \
    PATH="/app/.venv/bin:${PATH}"

EXPOSE 8080

# Production entrypoint: one worker, no reload (SQLite single-writer).
CMD ["uv", "run", "--no-sync", "uvicorn", "mintmory.api.app:app", \
     "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
