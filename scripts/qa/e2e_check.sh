#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-.venv/bin/python}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8010}"
API_URL="http://${API_HOST}:${API_PORT}"
QUICK=0
WITH_REAL=0
SKIP_API=0
START_API=1

usage() {
  cat <<'EOF'
Usage: scripts/qa/e2e_check.sh [options]

Options:
  --quick         Run a 5-question dry-run instead of the full 50-question baseline.
  --with-real     Also run the 8-question safety/boundary real LLM generation check.
  --skip-api      Skip FastAPI health and /ask checks.
  --no-start-api  Do not start a temporary local API if /health is unavailable.
  -h, --help      Show this help.

Environment:
  PYTHON          Python executable, default .venv/bin/python
  API_HOST        API host, default 127.0.0.1
  API_PORT        API port, default 8010
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick)
      QUICK=1
      shift
      ;;
    --with-real)
      WITH_REAL=1
      shift
      ;;
    --skip-api)
      SKIP_API=1
      shift
      ;;
    --no-start-api)
      START_API=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

api_pid=""
cleanup() {
  if [[ -n "$api_pid" ]]; then
    kill "$api_pid" >/dev/null 2>&1 || true
    wait "$api_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

need_cmd docker
need_cmd curl
[[ -x "$PYTHON" ]] || fail "python executable not found or not executable: $PYTHON"

log "Static checks"
"$PYTHON" -m py_compile \
  scripts/qa/agent_runner.py \
  scripts/qa/agent_router.py \
  scripts/qa/agent_policy.py \
  scripts/qa/agent_tools.py \
  scripts/qa/agent_trace.py \
  scripts/qa/kgrag_answer.py \
  scripts/qa/evaluate_qa.py \
  scripts/qa/kgrag_api.py
python -m json.tool config/graph/curated_entity_alias_map.json >/tmp/asd_kgrag_alias_check.json
"$PYTHON" - <<'PY'
import json
from pathlib import Path

path = Path("scripts/qa/eval_questions.jsonl")
rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
ids = [row["id"] for row in rows]
if len(ids) != len(set(ids)):
    raise SystemExit("duplicate eval question ids")
print(f"eval_questions: {len(rows)} rows, {len(set(row['category'] for row in rows))} categories")
PY

log "Starting Neo4j and Qdrant"
docker compose up -d neo4j qdrant

log "Waiting for Qdrant"
for _ in {1..60}; do
  if curl -fsS "http://127.0.0.1:6333/collections" >/tmp/asd_kgrag_qdrant_collections.json 2>/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:6333/collections" >/tmp/asd_kgrag_qdrant_collections.json

log "Checking Neo4j and Qdrant data"
"$PYTHON" - <<'PY'
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "asd-kgrag-local"))
try:
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        chunks = session.run("MATCH (c:Chunk) RETURN count(c) AS c").single()["c"]
        if nodes <= 0 or rels <= 0 or chunks <= 0:
            raise SystemExit(f"Neo4j looks empty: nodes={nodes}, rels={rels}, chunks={chunks}")
        print(f"neo4j: nodes={nodes}, rels={rels}, chunks={chunks}")
finally:
    driver.close()

client = QdrantClient(url="http://localhost:6333")
info = client.get_collection("asd_kgrag_chunks")
points = int(info.points_count or 0)
if points <= 0:
    raise SystemExit("Qdrant collection asd_kgrag_chunks looks empty")
print(f"qdrant: asd_kgrag_chunks points={points}")
PY

if [[ "$SKIP_API" -eq 0 ]]; then
  log "Checking FastAPI /health"
  if ! curl -fsS "${API_URL}/health" >/tmp/asd_kgrag_api_health.json 2>/dev/null; then
    if [[ "$START_API" -eq 0 ]]; then
      fail "API is not reachable at ${API_URL}; rerun without --no-start-api or use --skip-api"
    fi
    log "Starting temporary API on ${API_URL}"
    "$PYTHON" scripts/qa/kgrag_api.py --host "$API_HOST" --port "$API_PORT" >/tmp/asd_kgrag_api.log 2>&1 &
    api_pid="$!"
    for _ in {1..120}; do
      if curl -fsS "${API_URL}/health" >/tmp/asd_kgrag_api_health.json 2>/dev/null; then
        break
      fi
      if ! kill -0 "$api_pid" >/dev/null 2>&1; then
        sed -n '1,120p' /tmp/asd_kgrag_api.log >&2 || true
        fail "temporary API process exited before becoming healthy"
      fi
      sleep 1
    done
    curl -fsS "${API_URL}/health" >/tmp/asd_kgrag_api_health.json
  fi

  log "Checking FastAPI /ask dry_run"
  curl -fsS -X POST "${API_URL}/ask" \
    -H 'Content-Type: application/json' \
    -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true,"context_k":4,"graph_evidence_k":2}' \
    >/tmp/asd_kgrag_api_ask.json
  "$PYTHON" - <<'PY'
import json
payload = json.loads(open("/tmp/asd_kgrag_api_ask.json", encoding="utf-8").read())
ctx = payload.get("context") or {}
contexts = ctx.get("contexts") or []
relations = ctx.get("relations") or []
if not contexts:
    raise SystemExit("/ask dry_run returned no contexts")
if not relations:
    raise SystemExit("/ask dry_run returned no graph relations")
print(f"api ask: contexts={len(contexts)}, relations={len(relations)}")
PY
fi

log "Checking CLI dry-run"
"$PYTHON" scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 4 \
  --graph-evidence-k 2 \
  >/tmp/asd_kgrag_cli_dry_run.txt

log "Checking agent toolized dry-run"
"$PYTHON" scripts/qa/agent_runner.py \
  --query "孩子语言少、不太看人，是不是就能判断为自闭症?" \
  --dry-run \
  --trace-out /tmp/asd_kgrag_agent_trace.json \
  >/tmp/asd_kgrag_agent_dry_run.txt
"$PYTHON" - <<'PY'
import json
trace = json.loads(open("/tmp/asd_kgrag_agent_trace.json", encoding="utf-8").read())
steps = [step.get("name") for step in trace.get("steps") or []]
required = [
    "classify_query_intent",
    "expand_query",
    "retrieve_context",
    "inspect_evidence",
    "plan_followup_retrieval",
    "retrieve_context_followup_1",
    "merge_followup_evidence",
    "draft_answer",
    "validate_answer",
]
missing = [name for name in required if name not in steps]
if missing:
    raise SystemExit(f"agent trace missing steps: {missing}")
print(f"agent trace: {len(steps)} steps")
PY

log "Running batch dry-run evaluation"
dry_args=(--dry-run --context-k 6 --graph-evidence-k 4)
if [[ "$QUICK" -eq 1 ]]; then
  dry_args+=(--limit 5)
fi
"$PYTHON" scripts/qa/evaluate_qa.py "${dry_args[@]}"

if [[ "$WITH_REAL" -eq 1 ]]; then
  log "Running safety/boundary real LLM evaluation"
  "$PYTHON" scripts/qa/evaluate_qa.py \
    --ids \
      safety_direct_treatment \
      safety_medication_advice \
      safety_stop_professional_eval \
      safety_single_symptom_diagnosis \
      safety_diet_cure_claim \
      safety_hyperbaric_oxygen \
      qa_boundary_research_context \
      qa_boundary_evidence_level \
    --context-k 6 \
    --graph-evidence-k 4 \
    --retries 1 \
    --retry-delay 3
fi

log "E2E check passed"
