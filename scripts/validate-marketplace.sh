#!/usr/bin/env bash
set -euo pipefail

MARKETPLACE=".claude-plugin/marketplace.json"
PLUGINS_DIR="plugins"
errors=0

# --- Helpers ---
fail() {
  echo "ERROR: $1" >&2
  errors=$((errors + 1))
}

# --- File existence & valid JSON ---
if [[ ! -f "$MARKETPLACE" ]]; then
  echo "ERROR: $MARKETPLACE not found" >&2
  exit 1
fi

if ! jq empty "$MARKETPLACE" 2>/dev/null; then
  echo "ERROR: $MARKETPLACE is not valid JSON" >&2
  exit 1
fi

# --- Required top-level fields ---
name=$(jq -r '.name // empty' "$MARKETPLACE")
[[ -z "$name" ]] && fail "missing top-level 'name' string"

owner_name=$(jq -r '.owner.name // empty' "$MARKETPLACE")
[[ -z "$owner_name" ]] && fail "missing 'owner.name' string"

plugins_type=$(jq -r '.plugins | type' "$MARKETPLACE")
[[ "$plugins_type" != "array" ]] && fail "'plugins' must be an array"

# --- Per-plugin validation ---
plugin_count=$(jq '.plugins | length' "$MARKETPLACE")
for i in $(seq 0 $((plugin_count - 1))); do
  p_name=$(jq -r ".plugins[$i].name // empty" "$MARKETPLACE")
  p_source=$(jq -r ".plugins[$i].source // empty" "$MARKETPLACE")
  p_desc=$(jq -r ".plugins[$i].description // empty" "$MARKETPLACE")

  [[ -z "$p_name" ]]   && fail "plugins[$i]: missing 'name'"
  [[ -z "$p_source" ]] && fail "plugins[$i]: missing 'source'"
  [[ -z "$p_desc" ]]   && fail "plugins[$i]: missing 'description'"

  if [[ -n "$p_source" && ! -d "$p_source" ]]; then
    fail "plugins[$i]: source directory '$p_source' does not exist"
  fi
done

# --- Plugin coverage check ---
registered_sources=$(jq -r '.plugins[].source' "$MARKETPLACE")

for dir in "$PLUGINS_DIR"/*/; do
  dir_name=$(basename "$dir")
  expected="./plugins/$dir_name"
  if ! echo "$registered_sources" | grep -qxF "$expected"; then
    fail "plugin directory '$dir_name' is not listed in $MARKETPLACE (expected source: $expected)"
  fi
done

# --- Result ---
if [[ $errors -gt 0 ]]; then
  echo "Validation failed with $errors error(s)" >&2
  exit 1
fi

echo "Marketplace validation passed"
