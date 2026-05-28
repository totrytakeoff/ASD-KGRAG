#!/usr/bin/env bash
set -euo pipefail

MAIN_JSONL="${1:-data/processed/extraction_full_ab_nonbook_v5/chunk_extractions.jsonl}"
RETRY_JSONL="${2:-data/processed/extraction_full_ab_nonbook_v5_retry/chunk_extractions.jsonl}"
RETRY_INCREMENTAL_JSONL="${3:-data/processed/extraction_full_ab_nonbook_v5_retry_incremental/chunk_extractions.jsonl}"
MERGED_JSONL="${MERGED_JSONL:-data/processed/extraction_full_ab_nonbook_v5_merged.jsonl}"
REVALIDATED_JSONL="${REVALIDATED_JSONL:-data/processed/extraction_full_ab_nonbook_v5_merged_revalidated.jsonl}"
NORMALIZED_DIR="${NORMALIZED_DIR:-data/processed/normalized_full_ab_nonbook_v5_current_revalidated}"
NEO4J_DIR="${NEO4J_DIR:-data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated}"
REPORT_DIR="${REPORT_DIR:-data/processed/extraction_full_ab_nonbook_v5_current_revalidated_report}"
CHUNKS_JSONL="${CHUNKS_JSONL:-data/processed/chunks_extractable_full_ab_nonbook.jsonl}"

inputs=("$MAIN_JSONL")
if [[ -s "$RETRY_JSONL" ]]; then
  inputs+=("$RETRY_JSONL")
fi
if [[ -s "$RETRY_INCREMENTAL_JSONL" ]]; then
  inputs+=("$RETRY_INCREMENTAL_JSONL")
fi

python scripts/extraction/merge_extraction_runs.py \
  --inputs "${inputs[@]}" \
  --output "$MERGED_JSONL"

python scripts/extraction/revalidate_extraction_run.py \
  --input "$MERGED_JSONL" \
  --output "$REVALIDATED_JSONL"

python scripts/extraction/normalize_extractions.py \
  --input "$REVALIDATED_JSONL" \
  --output "$NORMALIZED_DIR"

python scripts/graph/export_neo4j_import.py \
  --entities "$NORMALIZED_DIR/entities.jsonl" \
  --relations "$NORMALIZED_DIR/relations.jsonl" \
  --evidence "$NORMALIZED_DIR/evidence.jsonl" \
  --chunks "$CHUNKS_JSONL" \
  --output "$NEO4J_DIR"

python scripts/extraction/summarize_extraction_run.py \
  --input "$REVALIDATED_JSONL" \
  --output "$REPORT_DIR" \
  --sample-size "${SAMPLE_SIZE:-60}"
