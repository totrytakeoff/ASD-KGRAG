#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

INPUT="${1:-data/processed/chunks_extractable_full_ab_nonbook.jsonl}"
MAIN_OUTPUT_DIR="${2:-data/processed/extraction_full_ab_nonbook_v5}"
RETRY_OUTPUT_DIR="${3:-data/processed/extraction_full_ab_nonbook_v5_retry_incremental}"
RETRY_INPUT="${4:-data/processed/chunks_extractable_full_ab_nonbook_retry_transient.jsonl}"

MAIN_JSONL="${MAIN_OUTPUT_DIR}/chunk_extractions.jsonl"
RETRY_JSONL="${RETRY_OUTPUT_DIR}/chunk_extractions.jsonl"
SOURCE_EXTRACTION_JSONL="${SOURCE_EXTRACTION_JSONL:-$MAIN_JSONL}"

BATCH_SIZE="${BATCH_SIZE:-30}"
WORKERS="${WORKERS:-2}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-1200}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-180}"
MAX_RETRIES="${MAX_RETRIES:-2}"
RETRY_SLEEP="${RETRY_SLEEP:-8}"
SUMMARY_EVERY="${SUMMARY_EVERY:-10}"
MAX_TOKENS="${MAX_TOKENS:-1200}"
SYSTEM_PROMPT="${SYSTEM_PROMPT:-scripts/extraction/entity_relation_system_prompt_v6_light.txt}"
RESPONSE_FORMAT="${RESPONSE_FORMAT:-json_object}"
REQUEST_SLEEP="${REQUEST_SLEEP:-0.05}"
RETRY_FILTER="${RETRY_FILTER:-transient}"
REFRESH_EVERY_BATCHES="${REFRESH_EVERY_BATCHES:-10}"
SLEEP_BETWEEN_BATCHES="${SLEEP_BETWEEN_BATCHES:-2}"
MAX_NO_PROGRESS="${MAX_NO_PROGRESS:-3}"
LOG_DIR="${LOG_DIR:-data/logs/extraction}"
LOCK_DIR="${LOCK_DIR:-data/logs/extraction/retry_until_complete.lock}"

MODEL="${LLM_MODEL:-deepseek-ai/DeepSeek-V4-Flash}"
BASE_URL="${LLM_BASE_URL:-}"

mkdir -p "$LOG_DIR" "$RETRY_OUTPUT_DIR"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/retry_until_complete_${RUN_ID}.log"

log() {
  printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"
}

count_progress() {
  python3 - "$RETRY_INPUT" "$RETRY_JSONL" <<'PY'
import json
import sys
from pathlib import Path

input_path = Path(sys.argv[1])
jsonl_path = Path(sys.argv[2])

total = sum(1 for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip())
seen = set()
ok = 0
err = 0
if jsonl_path.exists():
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        chunk_id = row.get("chunk_id")
        if chunk_id:
            seen.add(chunk_id)
        if row.get("status") == "ok":
            ok += 1
        elif row.get("status") == "error":
            err += 1

print(json.dumps({"total": total, "attempted": len(seen), "ok": ok, "error": err}, ensure_ascii=False))
PY
}

next_start_index() {
  python3 - "$RETRY_INPUT" "$RETRY_JSONL" <<'PY'
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
}

if [[ -z "${LLM_API_KEY:-}" ]]; then
  log "LLM_API_KEY is not set; aborting."
  exit 1
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  existing_pid="$(cat "${LOCK_DIR}/pid" 2>/dev/null || true)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    log "another retry daemon is already running: pid=${existing_pid}"
    exit 3
  fi
  log "removing stale retry lock: ${LOCK_DIR}"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
fi
printf '%s\n' "$$" >"${LOCK_DIR}/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

log "run_id=${RUN_ID}"
log "input=${INPUT}"
log "main_output=${MAIN_OUTPUT_DIR}"
log "source_extraction=${SOURCE_EXTRACTION_JSONL}"
log "retry_output=${RETRY_OUTPUT_DIR}"
log "retry_input=${RETRY_INPUT}"
log "batch_size=${BATCH_SIZE} workers=${WORKERS} request_timeout=${REQUEST_TIMEOUT} timeout=${TIMEOUT_SECONDS} max_retries=${MAX_RETRIES}"
log "retry_filter=${RETRY_FILTER}"
log "log_file=${LOG_FILE}"

filter_args=()
if [[ "$RETRY_FILTER" == "transient" ]]; then
  filter_args=(--transient-errors)
elif [[ "$RETRY_FILTER" != "all" ]]; then
  log "unknown RETRY_FILTER=${RETRY_FILTER}; expected transient or all"
  exit 4
fi

python3 scripts/extraction/build_retry_chunks.py \
  --input "$INPUT" \
  --extraction "$SOURCE_EXTRACTION_JSONL" \
  --output "$RETRY_INPUT" \
  "${filter_args[@]}" >>"$LOG_FILE" 2>&1

if [[ ! -s "$RETRY_INPUT" ]]; then
  log "no transient retry chunks; refreshing current outputs."
  EXTRA_EXTRACTION_JSONL="${RETRY_JSONL}${EXTRA_EXTRACTION_JSONL:+ ${EXTRA_EXTRACTION_JSONL}}" \
    bash scripts/extraction/refresh_current_outputs.sh >>"$LOG_FILE" 2>&1
  log "complete."
  exit 0
fi

batch_no=0
no_progress=0
prev_attempted=-1

while true; do
  progress="$(count_progress)"
  attempted="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["attempted"])' "$progress")"
  total="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["total"])' "$progress")"
  ok="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["ok"])' "$progress")"
  err="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["error"])' "$progress")"

  log "retry progress attempted=${attempted}/${total} ok=${ok} error=${err}"
  if [[ "$attempted" -ge "$total" ]]; then
    log "all retry chunks attempted; refreshing final current outputs."
    EXTRA_EXTRACTION_JSONL="${RETRY_JSONL}${EXTRA_EXTRACTION_JSONL:+ ${EXTRA_EXTRACTION_JSONL}}" \
      bash scripts/extraction/refresh_current_outputs.sh >>"$LOG_FILE" 2>&1
    log "complete."
    exit 0
  fi

  if [[ "$attempted" -eq "$prev_attempted" ]]; then
    no_progress=$((no_progress + 1))
  else
    no_progress=0
  fi
  prev_attempted="$attempted"
  if [[ "$no_progress" -ge "$MAX_NO_PROGRESS" ]]; then
    log "no retry progress for ${MAX_NO_PROGRESS} consecutive loops; aborting."
    exit 2
  fi

  start_index="$(next_start_index)"
  batch_no=$((batch_no + 1))
  log "starting retry batch ${batch_no} start_index=${start_index}"

  set +e
  timeout "${TIMEOUT_SECONDS}s" python3 scripts/extraction/extract_entities_relations.py \
    --backend openai \
    --model "$MODEL" \
    ${BASE_URL:+--base-url "$BASE_URL"} \
    --system-prompt "$SYSTEM_PROMPT" \
    --site-url https://localhost \
    --app-name ASD-KGRAG \
    --input "$RETRY_INPUT" \
    --output "$RETRY_OUTPUT_DIR" \
    --start-index "$start_index" \
    --limit "$BATCH_SIZE" \
    --resume \
    --request-timeout "$REQUEST_TIMEOUT" \
    --sleep-seconds "$REQUEST_SLEEP" \
    --max-retries "$MAX_RETRIES" \
    --retry-sleep-seconds "$RETRY_SLEEP" \
    --max-tokens "$MAX_TOKENS" \
    --response-format "$RESPONSE_FORMAT" \
    --workers "$WORKERS" \
    --summary-every "$SUMMARY_EVERY" >>"$LOG_FILE" 2>&1
  status=$?
  set -e
  log "retry batch ${batch_no} exit_status=${status}"

  if (( batch_no % REFRESH_EVERY_BATCHES == 0 )); then
    log "refreshing current outputs after ${batch_no} retry batches"
    EXTRA_EXTRACTION_JSONL="${RETRY_JSONL}${EXTRA_EXTRACTION_JSONL:+ ${EXTRA_EXTRACTION_JSONL}}" \
      bash scripts/extraction/refresh_current_outputs.sh >>"$LOG_FILE" 2>&1
    log "refresh done"
  fi

  sleep "$SLEEP_BETWEEN_BATCHES"
done
