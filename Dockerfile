# syntax=docker/dockerfile:1.7

# --- build: resolve locked dependencies into a virtualenv -------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- runtime: only the virtualenv, non-root -----------------------------------------------------
FROM python:3.12-slim AS runtime

ARG GIT_COMMIT=unknown
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    CONFIG_PATH=/config/config.yaml \
    LOG_FORMAT=json \
    GIT_COMMIT=${GIT_COMMIT}

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /data /config \
    && chown app:app /data

COPY --from=builder --chown=app:app /app/.venv /app/.venv

USER app
WORKDIR /app
VOLUME ["/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
    CMD ["toad-userbot", "healthcheck"]

ENTRYPOINT ["toad-userbot"]
CMD ["run"]
