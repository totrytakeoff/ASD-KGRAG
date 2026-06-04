#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

INPUT="${1:-data/processed/chunks_extractable_full_ab_nonbook.jsonl}"
OUTPUT="${2:-data/processed/extraction_full_ab_nonbook_v5}"
JSONL="${OUTPUT}/chunk_extractions.jsonl"

MODE="${MODE:-throughput}"
BATCH_SIZE="${BATCH_SIZE:-30}"
WORKERS="${WORKERS:-3}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-90}"
MAX_RETRIES="${MAX_RETRIES:-0}"
SUMMARY_EVERY="${SUMMARY_EVERY:-10}"
REFRESH_EVERY_BATCHES="${REFRESH_EVERY_BATCHES:-10}"
SLEEP_BETWEEN_BATCHES="${SLEEP_BETWEEN_BATCHES:-2}"
MAX_NO_PROGRESS="${MAX_NO_PROGRESS:-3}"
LOG_DIR="${LOG_DIR:-data/logs/extraction}"
LOCK_DIR="${LOCK_DIR:-data/logs/extraction/run_until_complete.lock}"

mkdir -p "$LOG_DIR"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/run_until_complete_${RUN_ID}.log"

count_progress() {
  python3 - "$INPUT" "$JSONL" <<'PY'
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

log() {
  printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"
}

if [[ -z "${LLM_API_KEY:-}" ]]; then
  log "LLM_API_KEY is not set; aborting."
  exit 1
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  existing_pid="$(cat "${LOCK_DIR}/pid" 2>/dev/null || true)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    log "another extraction daemon is already running: pid=${existing_pid}"
    exit 3
  fi
  log "removing stale lock: ${LOCK_DIR}"
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR"
fi
printf '%s\n' "$$" >"${LOCK_DIR}/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

log "run_id=${RUN_ID}"
log "input=${INPUT}"
log "output=${OUTPUT}"
log "mode=${MODE} batch_size=${BATCH_SIZE} workers=${WORKERS} request_timeout=${REQUEST_TIMEOUT} timeout=${TIMEOUT_SECONDS}"
log "log_file=${LOG_FILE}"

batch_no=0
no_progress=0
prev_attempted=-1

while true; do
  progress="$(count_progress)"
  attempted="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["attempted"])' "$progress")"
  total="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["total"])' "$progress")"
  ok="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["ok"])' "$progress")"
  err="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["error"])' "$progress")"

  log "progress attempted=${attempted}/${total} ok=${ok} error=${err}"
  if [[ "$attempted" -ge "$total" ]]; then
    log "all chunks attempted; refreshing final current outputs."
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
    log "no progress for ${MAX_NO_PROGRESS} consecutive loops; aborting."
    exit 2
  fi

  batch_no=$((batch_no + 1))
  log "starting batch ${batch_no}"
  set +e
  MODE="$MODE" \
  BATCH_SIZE="$BATCH_SIZE" \
  WORKERS="$WORKERS" \
  TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
  REQUEST_TIMEOUT="$REQUEST_TIMEOUT" \
  MAX_RETRIES="$MAX_RETRIES" \
  SUMMARY_EVERY="$SUMMARY_EVERY" \
    bash scripts/extraction/run_next_extraction_batch.sh >>"$LOG_FILE" 2>&1
  status=$?
  set -e
  log "batch ${batch_no} exit_status=${status}"

  if (( batch_no % REFRESH_EVERY_BATCHES == 0 )); then
    log "refreshing current outputs after ${batch_no} batches"
    bash scripts/extraction/refresh_current_outputs.sh >>"$LOG_FILE" 2>&1
    log "refresh done"
  fi

  sleep "$SLEEP_BETWEEN_BATCHES"
done
