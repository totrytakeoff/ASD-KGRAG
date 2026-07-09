#!/usr/bin/env python3
"""Compare baseline KGRAG and controlled agent KGRAG dry-run behavior."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from agent_tools import run_toolized_agent  # noqa: E402
from agent_trace import AgentTrace  # noqa: E402
from evaluate_qa import DEFAULT_INPUT, evaluate_result, open_shared_resources, read_jsonl, write_jsonl  # noqa: E402
from kgrag_answer import answer_query, default_namespace, load_dotenv  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "data" / "qa_compare"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Compare baseline KGRAG vs agent KGRAG dry-run results.")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--limit", type=int, default=0, help="Compare only the first N questions.")
    ap.add_argument("--ids", nargs="*", default=[], help="Compare only matching question ids.")
    ap.add_argument("--context-k", type=int, default=6)
    ap.add_argument("--graph-evidence-k", type=int, default=4)
    ap.add_argument("--retrieval-k", type=int, default=20)
    ap.add_argument("--relation-k", type=int, default=30)
    ap.add_argument("--relation-evidence-k", type=int, default=6)
    ap.add_argument("--graph-evidence-pool-k", type=int, default=30)
    ap.add_argument("--max-chars-per-chunk", type=int, default=900)
    return ap.parse_args()


def selected_questions(args: argparse.Namespace) -> list[dict]:
    questions = read_jsonl(args.input)
    if args.ids:
        wanted = set(args.ids)
        questions = [row for row in questions if row.get("id") in wanted]
    if args.limit > 0:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit("No questions selected.")
    return questions


def qa_namespace(question: dict, args: argparse.Namespace) -> SimpleNamespace:
    return default_namespace(
        query=str(question.get("query") or "").strip(),
        keywords=question.get("keywords") or [],
        dry_run=True,
        context_k=args.context_k,
        graph_evidence_k=args.graph_evidence_k,
        retrieval_k=args.retrieval_k,
        relation_k=args.relation_k,
        relation_evidence_k=args.relation_evidence_k,
        graph_evidence_pool_k=args.graph_evidence_pool_k,
        max_chars_per_chunk=args.max_chars_per_chunk,
    )


def metric(row: dict, key: str, default: Any = 0) -> Any:
    return (row.get("metrics") or {}).get(key, default)


def check(row: dict, key: str) -> bool:
    return bool((row.get("checks") or {}).get(key))


def classify_delta(baseline_eval: dict, agent_eval: dict) -> str:
    if not baseline_eval.get("ok") and agent_eval.get("ok"):
        return "agent_win"
    if baseline_eval.get("ok") and not agent_eval.get("ok"):
        return "agent_regression"
    if not check(baseline_eval, "retrieved_graph") and check(agent_eval, "retrieved_graph"):
        return "agent_win"
    if check(baseline_eval, "retrieved_graph") and not check(agent_eval, "retrieved_graph"):
        return "agent_regression"
    if metric(agent_eval, "relations_count") > metric(baseline_eval, "relations_count"):
        return "agent_gain"
    if metric(agent_eval, "relations_count") < metric(baseline_eval, "relations_count"):
        return "agent_loss"
    return "tie"


def trace_step_names(trace: AgentTrace) -> list[str]:
    return [step.get("name", "") for step in trace.steps]


def compact_eval(row: dict) -> dict:
    return {
        "ok": row.get("ok"),
        "checks": row.get("checks") or {},
        "metrics": row.get("metrics") or {},
        "flags": row.get("flags") or {},
    }


def compare_one(question: dict, args: argparse.Namespace, driver, embed_model, qdrant_client) -> dict:
    ns = qa_namespace(question, args)

    baseline_start = time.time()
    baseline_result = answer_query(
        ns,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
    )
    baseline_eval = evaluate_result(question, baseline_result, time.time() - baseline_start)

    agent_trace = AgentTrace(query=ns.query)
    agent_start = time.time()
    agent_result = run_toolized_agent(
        ns,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
        trace=agent_trace,
    )
    agent_eval = evaluate_result(question, agent_result, time.time() - agent_start)

    agent_info = agent_result.get("agent") or {}
    route = agent_info.get("intent") or {}
    evidence = agent_info.get("evidence") or {}
    policy = evidence.get("answer_policy") or {}
    steps = trace_step_names(agent_trace)
    delta = {
        "classification": classify_delta(baseline_eval, agent_eval),
        "contexts_count": metric(agent_eval, "contexts_count") - metric(baseline_eval, "contexts_count"),
        "relations_count": metric(agent_eval, "relations_count") - metric(baseline_eval, "relations_count"),
        "graph_entities_count": metric(agent_eval, "graph_entities_count") - metric(baseline_eval, "graph_entities_count"),
        "elapsed_seconds": round(metric(agent_eval, "elapsed_seconds") - metric(baseline_eval, "elapsed_seconds"), 2),
        "followup_triggered": "retrieve_context_followup_1" in steps,
    }
    return {
        "id": question.get("id"),
        "category": question.get("category"),
        "query": ns.query,
        "baseline": compact_eval(baseline_eval),
        "agent": {
            **compact_eval(agent_eval),
            "route": route.get("route") or route.get("intent"),
            "retrieval_focus": route.get("retrieval_focus") or [],
            "answer_mode": policy.get("answer_mode"),
            "forbidden_claims": policy.get("forbidden_claims") or [],
            "trace_steps": steps,
        },
        "delta": delta,
    }


def summarize_compare(rows: list[dict]) -> dict:
    total = len(rows)
    buckets: dict[str, int] = {}
    by_category: dict[str, dict[str, int]] = {}
    route_counts: dict[str, int] = {}
    followup_count = 0
    relation_deltas = []
    elapsed_deltas = []

    for row in rows:
        classification = row["delta"]["classification"]
        buckets[classification] = buckets.get(classification, 0) + 1
        category = row.get("category") or "uncategorized"
        category_bucket = by_category.setdefault(category, {})
        category_bucket[classification] = category_bucket.get(classification, 0) + 1
        route = row["agent"].get("route") or "unknown"
        route_counts[route] = route_counts.get(route, 0) + 1
        followup_count += 1 if row["delta"].get("followup_triggered") else 0
        relation_deltas.append(int(row["delta"].get("relations_count") or 0))
        elapsed_deltas.append(float(row["delta"].get("elapsed_seconds") or 0.0))

    improved = buckets.get("agent_win", 0) + buckets.get("agent_gain", 0)
    regressed = buckets.get("agent_regression", 0) + buckets.get("agent_loss", 0)
    return {
        "total": total,
        "agent_improved": improved,
        "agent_regressed": regressed,
        "agent_tied": buckets.get("tie", 0),
        "classification_counts": buckets,
        "by_category": by_category,
        "route_counts": route_counts,
        "followup_triggered": {
            "count": followup_count,
            "rate": round(followup_count / total, 4) if total else 0.0,
        },
        "relation_delta": {
            "min": min(relation_deltas) if relation_deltas else 0,
            "max": max(relation_deltas) if relation_deltas else 0,
            "avg": round(sum(relation_deltas) / len(relation_deltas), 2) if relation_deltas else 0.0,
        },
        "elapsed_delta_seconds": {
            "min": min(elapsed_deltas) if elapsed_deltas else 0,
            "max": max(elapsed_deltas) if elapsed_deltas else 0,
            "avg": round(sum(elapsed_deltas) / len(elapsed_deltas), 2) if elapsed_deltas else 0.0,
        },
    }


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    questions = selected_questions(args)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir / f"{timestamp}_dry_run_compare"
    rows = []

    with ExitStack() as stack:
        try:
            driver, embed_model, qdrant_client = open_shared_resources(stack)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None

        for idx, question in enumerate(questions, 1):
            print(f"[{idx}/{len(questions)}] {question.get('id')}: {question.get('query')}", flush=True)
            rows.append(compare_one(question, args, driver, embed_model, qdrant_client))

    summary = summarize_compare(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "results.jsonl", rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
