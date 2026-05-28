#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-data/processed/chunks_extractable_full_ab_nonbook.jsonl}"
OUTPUT="${2:-data/processed/extraction_full_ab_nonbook_v5}"
BATCH_SIZE="${BATCH_SIZE:-200}"
TIMEOUT="${TIMEOUT:-180}"
MAX_RETRIES="${MAX_RETRIES:-4}"
RETRY_SLEEP="${RETRY_SLEEP:-5}"
REQUEST_SLEEP="${REQUEST_SLEEP:-0.05}"
SUMMARY_EVERY="${SUMMARY_EVERY:-10}"

if [[ -z "${LLM_API_KEY:-}" ]]; then
  echo "LLM_API_KEY is not set" >&2
  exit 1
fi

MODEL="${LLM_MODEL:-deepseek-ai/DeepSeek-V4-Flash}"
BASE_URL="${LLM_BASE_URL:-}"
TOTAL=$(wc -l < "$INPUT" | tr -d ' ')

mkdir -p "$OUTPUT"

START=0
while [[ "$START" -lt "$TOTAL" ]]; do
  echo "== batch start_index=${START} batch_size=${BATCH_SIZE} total=${TOTAL} =="
  python scripts/extraction/extract_entities_relations.py \
    --backend openai \
    --model "$MODEL" \
    ${BASE_URL:+--base-url "$BASE_URL"} \
    --site-url https://localhost \
    --app-name ASD-KGRAG \
    --input "$INPUT" \
    --output "$OUTPUT" \
    --start-index "$START" \
    --limit "$BATCH_SIZE" \
    --resume \
    --request-timeout "$TIMEOUT" \
    --sleep-seconds "$REQUEST_SLEEP" \
    --max-retries "$MAX_RETRIES" \
    --retry-sleep-seconds "$RETRY_SLEEP" \
    --summary-every "$SUMMARY_EVERY"
  START=$((START + BATCH_SIZE))
done

echo "finished output=${OUTPUT}"
