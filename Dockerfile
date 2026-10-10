# Lighthouse connector image for aria-runner: Chromium, the tap, Meltano, dbt.
#
#   docker build --build-arg ARIA_RUNNER_IMAGE=aria-runner:latest -t aria-connector-lighthouse .
#
# ARIA_RUNNER_IMAGE is the control-plane image; its source pins the runner version here.
#
# Cloud Run Job: python -m aria_runner execute --run-id <id>   (default command)
#
# Sessions arrive at run time from Cloud Storage; none are baked in.

ARG ARIA_RUNNER_IMAGE=aria-runner:latest
FROM ${ARIA_RUNNER_IMAGE} AS aria-runner

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    MELTANO_PROJECT_ROOT=/app/lighthouse \
    MELTANO_SEND_ANONYMOUS_USAGE_STATS=false \
    PATH=/app/lighthouse/.venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv==0.5.29 \
    && useradd --create-home --uid 10001 runner

COPY --from=aria-runner /app/pyproject.toml /app/README.md /app/aria-runner/
COPY --from=aria-runner /app/src /app/aria-runner/src

WORKDIR /app/lighthouse
COPY pyproject.toml meltano.yml README.md ./
COPY packages ./packages
COPY transform ./transform
COPY config ./config

RUN uv sync --no-dev \
    && playwright install --with-deps chromium \
    && meltano install \
    && .meltano/extractors/tap-lighthouse/venv/bin/playwright install chromium \
    && meltano --environment=development invoke dbt-bigquery:deps \
    && python -m aria_runner connectors export lighthouse --out /app/lighthouse/connector-manifest.json \
    && chown -R runner:runner /app/lighthouse /ms-playwright

USER runner

ENTRYPOINT ["python", "-m", "aria_runner"]
CMD ["execute"]
