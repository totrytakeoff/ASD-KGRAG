#!/usr/bin/env bash
# Workaround for vite-plus@0.2.1 ESM self-import cycle bug.
# The ESM build incorrectly imports from "vite-plus" (itself) instead of "vitest/config".
# This patch rewrites those imports. Safe to re-run after `vp install`.
set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)/node_modules/vite-plus/dist"

sed -i 's|from "vite-plus"|from "vitest/config"|g' "$DIR/index.js"
sed -i 's|from "vite-plus"|from "vitest/config"|g' "$DIR/define-config-DJUehepE.js"

echo "vite-plus ESM self-import patched."
