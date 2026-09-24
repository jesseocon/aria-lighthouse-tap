#!/usr/bin/env bash
# Run sync-property.sh for every slug in config/properties/registry.yml.
#
# Example:
#   ./scripts/sync-all.sh --tier both --start-date 2025-09-01 --end-date 2025-09-30
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SLUGS="$(
  uv run python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('scripts/lib')))
from registry import list_slugs
for slug in list_slugs():
    print(slug)
"
)"

if [[ -z "$SLUGS" ]]; then
  echo "No properties found in registry.yml" >&2
  exit 1
fi

count=0
while IFS= read -r slug; do
  [[ -z "$slug" ]] && continue
  count=$((count + 1))
done <<< "$SLUGS"

echo "==> Syncing ${count} properties from registry"

while IFS= read -r slug; do
  [[ -z "$slug" ]] && continue
  echo ""
  echo "========================================"
  echo "Property: ${slug}"
  echo "========================================"
  "${REPO_ROOT}/scripts/sync-property.sh" "$slug" "$@"
done <<< "$SLUGS"

echo ""
echo "==> All properties complete"
