#!/usr/bin/env bash
# Run singer-playwright workshop from the Lighthouse Meltano project root.
# Ensures workshop/page_scripts.js and workshop-runs/ resolve correctly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export MELTANO_PROJECT_ROOT="$ROOT"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <workshop subcommand> [args...]" >&2
  echo "Example: $0 start --storage-state storage_state.json --detach" >&2
  exit 1
fi

exec uv run python -m singer_playwright workshop "$@"
