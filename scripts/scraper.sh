#!/usr/bin/env bash
# Lighthouse scraper iteration helpers (workshop + codegen).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export MELTANO_PROJECT_ROOT="$ROOT"

usage() {
  cat <<EOF
Usage: $0 <command> [args...]

Commands:
  start          Start workshop daemon (pass through args, e.g. --storage-state storage_state.json --detach)
  stop           Stop workshop daemon
  observe        Observe page model (optional: --frame-url-pattern, --label)
  goto           Navigate (requires --url or pass URL as second arg)
  extract        Extract table (pass workshop extract args)
  recipe-save    Save recipe from brief (requires --brief path)
  codegen        Generate stream modules from recipe (requires --recipe path)
  evaluate       Evaluate brief success criteria (requires --brief, --records JSON)

Examples:
  $0 start --storage-state storage_state.json --detach
  $0 goto --url "\$(uv run python -c "from singer_playwright.workshop.brief import load_brief; print(load_brief('briefs/strategy-snapshot.yaml').render_url())")"
  $0 extract --frame-url-pattern 'spider\\.kriyarevgen\\.com' --selector 'table.analytics.day-by-day' --limit 5
  $0 recipe-save --brief briefs/strategy-snapshot.yaml --records '[]'
  $0 codegen --recipe workshop-runs/<run_id>/recipe.json --output-dir packages/tap-lighthouse/tap_lighthouse

Workshop JS: workshop/page_scripts.js (Lighthouse-specific table heuristics)
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift

case "$cmd" in
  start|stop|observe|goto|act|extract|screenshot)
    exec uv run python -m singer_playwright workshop "$cmd" "$@"
    ;;
  recipe-save)
    exec uv run python -m singer_playwright workshop recipe save "$@"
    ;;
  codegen)
    exec uv run python -m singer_playwright workshop codegen "$@"
    ;;
  evaluate)
    exec uv run python -m singer_playwright workshop evaluate "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
