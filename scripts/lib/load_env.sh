#!/usr/bin/env bash
# Source repo env files without overriding variables already set in the shell.
load_repo_env() {
  local repo_root="$1"
  local file

  for file in "${repo_root}/.env" "${repo_root}/.env.local"; do
    if [[ -f "$file" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$file"
      set +a
    fi
  done

  if [[ -n "${TARGET_BIGQUERY_CREDENTIALS_PATH:-}" ]]; then
    export DBT_BIGQUERY_KEYFILE="${DBT_BIGQUERY_KEYFILE:-$TARGET_BIGQUERY_CREDENTIALS_PATH}"
  fi

  if [[ -n "${DBT_BIGQUERY_KEYFILE:-}" || -n "${TARGET_BIGQUERY_CREDENTIALS_PATH:-}" ]]; then
    export DBT_BIGQUERY_AUTH_METHOD="${DBT_BIGQUERY_AUTH_METHOD:-service-account}"
  else
    export DBT_BIGQUERY_AUTH_METHOD="${DBT_BIGQUERY_AUTH_METHOD:-oauth}"
  fi
}

require_bigquery_auth() {
  local method="${DBT_BIGQUERY_AUTH_METHOD:-oauth}"
  local keyfile="${DBT_BIGQUERY_KEYFILE:-${TARGET_BIGQUERY_CREDENTIALS_PATH:-}}"

  if [[ "$method" == "service-account" ]]; then
    if [[ -z "$keyfile" ]]; then
      echo "ERROR: DBT_BIGQUERY_AUTH_METHOD=service-account but no credentials file is set." >&2
      echo "Set TARGET_BIGQUERY_CREDENTIALS_PATH in .env or export DBT_BIGQUERY_KEYFILE." >&2
      exit 1
    fi
    if [[ ! -f "$keyfile" ]]; then
      echo "ERROR: GCP credentials file not found: $keyfile" >&2
      exit 1
    fi
  fi
}
