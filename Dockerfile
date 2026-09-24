# Scheduled Meltano runs with Playwright Chromium pre-installed.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MELTANO_PROJECT_ROOT=/app \
    MELTANO_ENVIRONMENT=development

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml meltano.yml README.md ./
COPY packages ./packages
COPY transform ./transform
COPY config ./config

RUN pip install uv && \
    uv sync && \
    uv run playwright install --with-deps chromium && \
    uv run meltano install && \
    uv run meltano --environment=development invoke dbt-bigquery:deps

# Mount GCP service account + storage_state.json at runtime (never bake into image).
VOLUME ["/app/secrets"]

CMD ["uv", "run", "meltano", "--environment=development", "run", "tap-lighthouse", "target-bigquery", "dbt-bigquery:run"]
