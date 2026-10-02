#!/usr/bin/env bash
# Scrape Lighthouse once, then load every selected warehouse.
# No --environment: scrape into development, copy bronze to production, dbt both.
# --environment development|production: that warehouse only.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=scripts/lib/load_env.sh
source "${REPO_ROOT}/scripts/lib/load_env.sh"
load_repo_env "$REPO_ROOT"

usage() {
  cat <<EOF
Usage: $(basename "$0") <slug> [options]

Options:
  --environment development|production
                               One warehouse only. Omit to scrape once and
                               write both development and production.
  --start-date YYYY-MM-DD      Earliest as_of_date to scrape
  --end-date YYYY-MM-DD        Latest as_of_date to scrape (default: today)
  --keep-state                 Do not reset state when a date range is set
  --scrape-only                Load bronze only (no dbt)
  --transform-only             Run dbt only (bronze must already exist)
  --test                       Run dbt test after each transform
  -h, --help                   Show this help

When --start-date and --end-date are both set, the tap scrapes exactly that
as_of_date range. State is reset by default so the range is not skipped.
EOF
}

validate_iso_date() {
  local label="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "Invalid ${label} value: ${value} (expected YYYY-MM-DD)" >&2
    exit 1
  fi
}

validate_date_range() {
  if [[ -n "$START_DATE" && -n "$END_DATE" && "$START_DATE" > "$END_DATE" ]]; then
    echo "Invalid date range: start (${START_DATE}) must be on or before end (${END_DATE})" >&2
    exit 1
  fi
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 1
fi

SLUG="$1"
shift

ENVIRONMENT_SET=false
MELTANO_ENV=""
DO_SCRAPE=true
DO_TRANSFORM=true
RUN_TEST=false
START_DATE=""
END_DATE=""
RESET_STATE=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment)
      MELTANO_ENV="${2:-}"
      ENVIRONMENT_SET=true
      shift 2
      ;;
    --environment=*)
      MELTANO_ENV="${1#--environment=}"
      ENVIRONMENT_SET=true
      shift
      ;;
    --tier|--tier=*)
      echo "Use --environment development|production (replaces --tier)." >&2
      exit 1
      ;;
    --start-date)
      START_DATE="${2:-}"
      shift 2
      ;;
    --start-date=*)
      START_DATE="${1#--start-date=}"
      shift
      ;;
    --end-date)
      END_DATE="${2:-}"
      shift 2
      ;;
    --end-date=*)
      END_DATE="${1#--end-date=}"
      shift
      ;;
    --keep-state)
      RESET_STATE=false
      shift
      ;;
    --scrape-only)
      DO_SCRAPE=true
      DO_TRANSFORM=false
      shift
      ;;
    --transform-only)
      DO_SCRAPE=false
      DO_TRANSFORM=true
      shift
      ;;
    --test)
      RUN_TEST=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$ENVIRONMENT_SET" == "false" ]]; then
  TARGET_ENVS=(development production)
  SCRAPE_ENV="development"
else
  case "$MELTANO_ENV" in
    development | dev) MELTANO_ENV="development" ;;
    production | prod) MELTANO_ENV="production" ;;
    *)
      echo "Invalid --environment value: $MELTANO_ENV (expected development or production)" >&2
      exit 1
      ;;
  esac
  TARGET_ENVS=("$MELTANO_ENV")
  SCRAPE_ENV="$MELTANO_ENV"
fi

if [[ -n "$START_DATE" ]]; then
  validate_iso_date "--start-date" "$START_DATE"
fi
if [[ -n "$END_DATE" ]]; then
  validate_iso_date "--end-date" "$END_DATE"
fi
validate_date_range

HOTEL_ID="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field hotel_id)"
BRONZE_TABLE="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field bronze_table)"

# Singer bookmarks follow the environment that actually scrapes.
SCRAPE_STATE_ID="${SCRAPE_ENV}:tap-lighthouse-to-target-bigquery"
LAST_SCRAPE_SLUG_FILE="${REPO_ROOT}/.meltano/last-scrape-slug-${SCRAPE_ENV}"

bq_project_for() {
  uv run python scripts/lib/dbt_vars.py --slug "$SLUG" --environment "$1" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["bq_project"])'
}

clear_scrape_state() {
  uv run meltano --environment="$SCRAPE_ENV" state clear --force "$SCRAPE_STATE_ID"
}

run_scrape() {
  export TAP_LIGHTHOUSE_HOTEL_ID="$HOTEL_ID"

  if [[ -n "$START_DATE" ]]; then
    export TAP_LIGHTHOUSE_START_DATE="$START_DATE"
  else
    unset TAP_LIGHTHOUSE_START_DATE || true
  fi
  if [[ -n "$END_DATE" ]]; then
    export TAP_LIGHTHOUSE_END_DATE="$END_DATE"
  else
    unset TAP_LIGHTHOUSE_END_DATE || true
  fi

  local prior_slug=""
  if [[ -f "$LAST_SCRAPE_SLUG_FILE" ]]; then
    prior_slug="$(<"$LAST_SCRAPE_SLUG_FILE")"
  fi

  if [[ -n "$START_DATE" || -n "$END_DATE" ]] && [[ "$RESET_STATE" == "true" ]]; then
    echo "==> Resetting incremental state for ${SLUG} (date range backfill)"
    clear_scrape_state
  elif [[ -n "$prior_slug" && "$prior_slug" != "$SLUG" ]]; then
    echo "==> Switching property (${prior_slug} → ${SLUG}): clearing tap bookmarks"
    clear_scrape_state
  fi

  mkdir -p "$(dirname "$LAST_SCRAPE_SLUG_FILE")"
  echo "$SLUG" > "$LAST_SCRAPE_SLUG_FILE"

  local stream_maps bronze_parity_table bronze_budget_table bronze_forecast_table
  stream_maps="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field stream_maps)"
  bronze_parity_table="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field bronze_parity_table)"
  bronze_budget_table="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field bronze_budget_table)"
  bronze_forecast_table="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field bronze_forecast_table)"

  echo "==> Scraping hotel_id=${HOTEL_ID} once (${SCRAPE_ENV}) → bronze ${BRONZE_TABLE} + ${bronze_parity_table} + ${bronze_budget_table} + ${bronze_forecast_table}"
  if [[ -n "$START_DATE" && -n "$END_DATE" ]]; then
    echo "==> as_of_date range: ${START_DATE} .. ${END_DATE}"
  elif [[ -n "$START_DATE" ]]; then
    echo "==> as_of_date start: ${START_DATE} (through today)"
  elif [[ -n "$END_DATE" ]]; then
    echo "==> as_of_date end: ${END_DATE}"
  fi
  uv run meltano --environment="$SCRAPE_ENV" config set target-bigquery stream_maps "$stream_maps" --plugin-type loader
  uv run meltano --environment="$SCRAPE_ENV" run lighthouse-scrape-bigquery
}

copy_bronze() {
  local spec
  require_bigquery_auth
  spec="$(uv run python scripts/lib/property_info.py --slug "$SLUG" --field copy_spec)"
  echo "==> Copying bronze development → production (no second Lighthouse scrape)"
  uv run meltano --environment=development invoke dbt-bigquery:run-operation copy_bronze_tables --args "$spec"
}

run_transform() {
  local env="$1"
  local vars project
  require_bigquery_auth
  project="$(bq_project_for "$env")"
  export DBT_BIGQUERY_PROJECT="$project"
  export MELTANO_ENVIRONMENT="$env"
  vars="$(uv run python scripts/lib/dbt_vars.py --slug "$SLUG" --environment "$env")"

  echo "==> dbt run (${env} → ${project}) (auth=${DBT_BIGQUERY_AUTH_METHOD})"
  uv run meltano --environment="$env" invoke dbt-bigquery:run --vars "$vars"
  if [[ "$RUN_TEST" == "true" ]]; then
    uv run meltano --environment="$env" invoke dbt-bigquery:test --vars "$vars"
  fi
}

writes_both=false
if [[ "${#TARGET_ENVS[@]}" -eq 2 ]]; then
  writes_both=true
fi

if [[ "$DO_SCRAPE" == "true" ]]; then
  run_scrape
fi

if [[ "$writes_both" == "true" ]]; then
  copy_bronze
fi

if [[ "$DO_TRANSFORM" == "true" ]]; then
  for env in "${TARGET_ENVS[@]}"; do
    run_transform "$env"
  done
fi

echo "==> Done: ${SLUG}"
