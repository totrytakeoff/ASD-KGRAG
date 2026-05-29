#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-data/processed/chunks_extractable_full_ab_nonbook.jsonl}"
MAIN_OUTPUT_DIR="${2:-data/processed/extraction_full_ab_nonbook_v5}"
RETRY_OUTPUT_DIR="${3:-data/processed/extraction_full_ab_nonbook_v5_retry}"
MERGED_OUTPUT="${4:-data/processed/extraction_full_ab_nonbook_v5_merged.jsonl}"

MAIN_JSONL="${MAIN_OUTPUT_DIR}/chunk_extractions.jsonl"
RETRY_INPUT="data/processed/chunks_extractable_full_ab_nonbook_retry_timeout.jsonl"
RETRY_JSONL="${RETRY_OUTPUT_DIR}/chunk_extractions.jsonl"

MODEL="${LLM_MODEL:-deepseek-ai/DeepSeek-V4-Flash}"
BASE_URL="${LLM_BASE_URL:-}"
MAX_TOKENS="${MAX_TOKENS:-1200}"
SYSTEM_PROMPT="${SYSTEM_PROMPT:-scripts/extraction/entity_relation_system_prompt_v6_light.txt}"
RESPONSE_FORMAT="${RESPONSE_FORMAT:-json_object}"

python scripts/extraction/build_retry_chunks.py \
  --input "$INPUT" \
  --extraction "$MAIN_JSONL" \
  --output "$RETRY_INPUT" \
  --only-timeouts

if [[ ! -s "$RETRY_INPUT" ]]; then
  echo "no retry chunks"
  exit 0
fi

python scripts/extraction/extract_entities_relations.py \
  --backend openai \
  --model "$MODEL" \
  ${BASE_URL:+--base-url "$BASE_URL"} \
  --system-prompt "$SYSTEM_PROMPT" \
  --site-url https://localhost \
  --app-name ASD-KGRAG \
  --input "$RETRY_INPUT" \
  --output "$RETRY_OUTPUT_DIR" \
  --request-timeout 240 \
  --sleep-seconds 0.05 \
  --max-retries 5 \
  --retry-sleep-seconds 8 \
  --max-tokens "$MAX_TOKENS" \
  --response-format "$RESPONSE_FORMAT" \
  --summary-every 5

python scripts/extraction/merge_extraction_runs.py \
  --inputs "$MAIN_JSONL" "$RETRY_JSONL" \
  --output "$MERGED_OUTPUT"

echo "merged_output=${MERGED_OUTPUT}"
