#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-data/processed/chunks_extractable_full_ab_nonbook.jsonl}"
OUTPUT="${2:-data/processed/extraction_full_ab_nonbook_v5}"
MODE="${MODE:-balanced}"

if [[ "$MODE" == "throughput" ]]; then
  BATCH_SIZE="${BATCH_SIZE:-50}"
  TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"
  REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-60}"
  MAX_RETRIES="${MAX_RETRIES:-0}"
  RETRY_SLEEP="${RETRY_SLEEP:-2}"
  SUMMARY_EVERY="${SUMMARY_EVERY:-10}"
  MAX_TOKENS="${MAX_TOKENS:-1200}"
  SYSTEM_PROMPT="${SYSTEM_PROMPT:-scripts/extraction/entity_relation_system_prompt_v6_light.txt}"
  RESPONSE_FORMAT="${RESPONSE_FORMAT:-json_object}"
elif [[ "$MODE" != "balanced" ]]; then
  echo "unknown MODE=${MODE}; expected balanced or throughput" >&2
  exit 1
else
  BATCH_SIZE="${BATCH_SIZE:-25}"
  TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1200}"
  REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120}"
  MAX_RETRIES="${MAX_RETRIES:-2}"
  RETRY_SLEEP="${RETRY_SLEEP:-5}"
  SUMMARY_EVERY="${SUMMARY_EVERY:-5}"
  MAX_TOKENS="${MAX_TOKENS:-0}"
  SYSTEM_PROMPT="${SYSTEM_PROMPT:-scripts/extraction/entity_relation_system_prompt.txt}"
  RESPONSE_FORMAT="${RESPONSE_FORMAT:-json_object}"
fi
REQUEST_SLEEP="${REQUEST_SLEEP:-0.05}"

if [[ -z "${LLM_API_KEY:-}" ]]; then
  echo "LLM_API_KEY is not set" >&2
  exit 1
fi

MODEL="${LLM_MODEL:-deepseek-ai/DeepSeek-V4-Flash}"
BASE_URL="${LLM_BASE_URL:-}"
JSONL="${OUTPUT}/chunk_extractions.jsonl"

START_INDEX="$(
  python - "$INPUT" "$JSONL" <<'PY'
import json
import sys
from pathlib import Path

input_path = Path(sys.argv[1])
jsonl_path = Path(sys.argv[2])

ids = []
for line in input_path.read_text(encoding="utf-8").splitlines():
    if line.strip():
        ids.append(json.loads(line)["chunk_id"])

index = {chunk_id: i for i, chunk_id in enumerate(ids)}
seen = set()
if jsonl_path.exists():
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunk_id = json.loads(line).get("chunk_id")
            if chunk_id in index:
                seen.add(index[chunk_id])

next_index = 0
while next_index in seen:
    next_index += 1

print(next_index)
PY
)"

TOTAL="$(wc -l < "$INPUT" | tr -d ' ')"
if [[ "$START_INDEX" -ge "$TOTAL" ]]; then
  echo "all chunks attempted: total=${TOTAL}"
  exit 0
fi

echo "== next batch start_index=${START_INDEX} batch_size=${BATCH_SIZE} total=${TOTAL} timeout=${TIMEOUT_SECONDS}s =="

timeout "${TIMEOUT_SECONDS}s" python scripts/extraction/extract_entities_relations.py \
  --backend openai \
  --model "$MODEL" \
  ${BASE_URL:+--base-url "$BASE_URL"} \
  --system-prompt "$SYSTEM_PROMPT" \
  --site-url https://localhost \
  --app-name ASD-KGRAG \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --start-index "$START_INDEX" \
  --limit "$BATCH_SIZE" \
  --resume \
  --request-timeout "$REQUEST_TIMEOUT" \
  --sleep-seconds "$REQUEST_SLEEP" \
  --max-retries "$MAX_RETRIES" \
  --retry-sleep-seconds "$RETRY_SLEEP" \
  --max-tokens "$MAX_TOKENS" \
  --response-format "$RESPONSE_FORMAT" \
  --summary-every "$SUMMARY_EVERY"
