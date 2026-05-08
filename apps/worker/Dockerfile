# syntax=docker/dockerfile:1.7
# Built from the *repo root* — `docker build -f apps/worker/Dockerfile .`

FROM python:3.12-slim AS builder
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential libpq-dev curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY apps/worker/ ./apps/worker/
COPY apps/api/ ./apps/api/

RUN uv sync --package liftwork-worker --frozen --no-dev


FROM python:3.12-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 liftwork \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home liftwork

COPY --from=builder --chown=1000:1000 /app /app
USER 1000

EXPOSE 7879
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 7879))" || exit 1
CMD ["python", "-m", "liftwork_worker.main"]
