# SMARTPBL API image. Two stages: build the virtualenv with uv, then copy it into a slim
# runtime that has no uv, no build cache and no root user.
#   docker build -t smartpbl-api:local .

# --- build -------------------------------------------------------------------------------
FROM python:3.12.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies only (a cached layer, rebuilt when the lockfile changes), production
# group only: no pytest, ruff or pre-commit in the image. --locked fails if uv.lock is
# out of date with pyproject.toml instead of silently re-resolving.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# --- runtime -----------------------------------------------------------------------------
FROM python:3.12.13-slim AS runtime
# A fixed, unprivileged user: the process can't modify the app or the virtualenv.
RUN groupadd --system --gid 10001 smartpbl \
    && useradd --system --uid 10001 --gid smartpbl --no-create-home smartpbl
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY prompts ./prompts
COPY data ./data
COPY scripts ./scripts
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib
USER smartpbl
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# --no-server-header: don't advertise the server software (OWASP API8).
# --proxy-headers: take the client IP from X-Forwarded-For, but only from the addresses in
# FORWARDED_ALLOW_IPS (uvicorn reads it from the environment; default 127.0.0.1), so login
# rate limits see real clients behind a reverse proxy and nobody else can spoof the header.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--no-server-header", "--proxy-headers"]
