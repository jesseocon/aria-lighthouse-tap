# Scheduled Meltano runs with Playwright Chromium pre-installed.
#
# Build from meltano-taps parent directory (sibling aria-singer-playwright required):
#
#   docker build -f aria-lighthouse/Dockerfile -t aria-lighthouse .

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MELTANO_PROJECT_ROOT=/app/lighthouse \
    MELTANO_ENVIRONMENT=development

WORKDIR /app/lighthouse

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY aria-singer-playwright /app/aria-singer-playwright
COPY aria-lighthouse/pyproject.toml aria-lighthouse/meltano.yml aria-lighthouse/README.md ./
COPY aria-lighthouse/packages ./packages
COPY aria-lighthouse/transform ./transform
COPY aria-lighthouse/config ./config

RUN pip install uv && \
    uv sync && \
    uv run playwright install --with-deps chromium && \
    uv run meltano install && \
    uv run meltano --environment=development invoke dbt-bigquery:deps

# Mount GCP service account + storage_state.json at runtime (never bake into image).
VOLUME ["/app/lighthouse/secrets"]

CMD ["uv", "run", "meltano", "--environment=development", "run", "tap-lighthouse", "target-bigquery", "dbt-bigquery:run"]
