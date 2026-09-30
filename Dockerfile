# Build stage
FROM python:3.14-alpine3.22 AS builder

RUN pip install uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY ecs_dns_updater/ ./ecs_dns_updater/
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.14-alpine3.22

LABEL org.opencontainers.image.source=https://github.com/melvyndekort/ecs-dns-updater

COPY --from=builder /app/.venv /venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /app
COPY ecs_dns_updater/ ./ecs_dns_updater/

CMD ["python", "-m", "ecs_dns_updater.main"]
