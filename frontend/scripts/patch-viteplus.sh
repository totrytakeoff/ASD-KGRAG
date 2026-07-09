#!/usr/bin/env bash
# Workaround for vite-plus@0.2.1 ESM self-import cycle bug.
# The ESM build incorrectly imports from "vite-plus" (itself) instead of "vitest/config".
# This patch rewrites those imports. Safe to re-run after `vp install`.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)/node_modules/vite-plus/dist"

if [[ -d "$DIR" ]]; then
  find "$DIR" -maxdepth 1 -type f \( -name '*.js' -o -name '*.cjs' \) \
    -exec sed -i 's|from "vite-plus"|from "vitest/config"|g' {} +
fi

echo "vite-plus ESM self-import patched."
