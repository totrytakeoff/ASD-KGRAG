#!/usr/bin/env python3
"""Batch evaluation for the KGRAG QA prototype."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from kgrag_answer import answer_query, default_namespace, load_dotenv  # noqa: E402


DEFAULT_INPUT = ROOT / "scripts" / "qa" / "eval_questions.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "qa_eval"


GUARDRAIL_PATTERNS = [
    r"不能替代",
    r"专业评估",
    r"临床决策",
    r"医生",
    r"临床",
    r"个体化",
]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def has_any_term(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms if term)


def context_text(result: dict) -> str:
    context = result.get("context") or {}
    parts = []
    for item in context.get("contexts") or []:
        parts.extend(
            str(item.get(key) or "")
            for key in ("citation_id", "title", "chunk_id", "evidence_level", "retrieval")
        )
    for row in context.get("relations") or []:
        parts.extend(
            str(row.get(key) or "")
            for key in ("graph_id", "source", "source_type", "relation", "target", "target_type", "qa_usage")
        )
    return "\n".join(parts)


def answer_text(result: dict) -> str:
    return str(result.get("answer") or "")


def evaluate_result(question: dict, result: dict, elapsed_seconds: float) -> dict:
    ctx = result.get("context") or {}
    contexts = ctx.get("contexts") or []
    relations = ctx.get("relations") or []
    answer = answer_text(result)
    combined_context = context_text(result)
    expected_terms = question.get("expect_graph_terms") or []

    metrics = {
        "contexts_count": len(contexts),
        "relations_count": len(relations),
        "has_context_citations": any(item.get("citation_id") for item in contexts),
        "has_graph_relations": bool(relations),
        "has_expected_context_term": has_any_term(combined_context, expected_terms) if expected_terms else None,
        "answer_has_citation": bool(re.search(r"\[(?:C|G)\d+\]", answer)) if answer else None,
        "answer_has_context_citation": bool(re.search(r"\[C\d+\]", answer)) if answer else None,
        "answer_has_graph_citation": bool(re.search(r"\[G\d+\]", answer)) if answer else None,
        "answer_has_guardrail": has_any_term(answer, GUARDRAIL_PATTERNS) if answer else None,
        "elapsed_seconds": round(elapsed_seconds, 2),
    }

    checks = {
        "retrieved_context": metrics["contexts_count"] > 0,
        "retrieved_graph": metrics["relations_count"] > 0,
        "expected_term_seen": metrics["has_expected_context_term"] is not False,
        "answer_cited": metrics["answer_has_citation"] is not False,
        "guardrail_ok": (
            metrics["answer_has_guardrail"] is not False
            if question.get("requires_guardrail")
            else True
        ),
    }
    return {
        "id": question.get("id"),
        "category": question.get("category"),
        "query": question.get("query"),
        "dry_run": result.get("dry_run"),
        "ok": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
        "result": result,
    }


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    by_category: dict[str, dict] = {}
    for row in rows:
        category = row.get("category") or "uncategorized"
        bucket = by_category.setdefault(category, {"total": 0, "ok": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if row.get("ok") else 0

    metric_keys = [
        "contexts_count",
        "relations_count",
        "has_context_citations",
        "has_graph_relations",
        "has_expected_context_term",
        "answer_has_citation",
        "answer_has_context_citation",
        "answer_has_graph_citation",
        "answer_has_guardrail",
    ]
    aggregate = {}
    for key in metric_keys:
        values = [row["metrics"].get(key) for row in rows if row["metrics"].get(key) is not None]
        if not values:
            continue
        if isinstance(values[0], bool):
            aggregate[key] = {
                "passed": sum(1 for value in values if value),
                "total": len(values),
                "rate": round(sum(1 for value in values if value) / len(values), 4),
            }
        else:
            aggregate[key] = {
                "min": min(values),
                "max": max(values),
                "avg": round(sum(values) / len(values), 2),
            }

    return {
        "total": total,
        "ok": sum(1 for row in rows if row.get("ok")),
        "ok_rate": round(sum(1 for row in rows if row.get("ok")) / total, 4) if total else 0.0,
        "by_category": by_category,
        "metrics": aggregate,
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Evaluate KGRAG QA retrieval and answer quality.")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--limit", type=int, default=0, help="Evaluate only the first N questions.")
    ap.add_argument("--ids", nargs="*", default=[], help="Evaluate only matching question ids.")
    ap.add_argument("--dry-run", action="store_true", help="Skip LLM generation and evaluate retrieval only.")
    ap.add_argument("--context-k", type=int, default=6)
    ap.add_argument("--graph-evidence-k", type=int, default=4)
    ap.add_argument("--retrieval-k", type=int, default=20)
    ap.add_argument("--relation-k", type=int, default=30)
    ap.add_argument("--relation-evidence-k", type=int, default=6)
    ap.add_argument("--graph-evidence-pool-k", type=int, default=30)
    ap.add_argument("--max-chars-per-chunk", type=int, default=900)
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")

    questions = read_jsonl(args.input)
    if args.ids:
        wanted = set(args.ids)
        questions = [row for row in questions if row.get("id") in wanted]
    if args.limit > 0:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit("No questions selected.")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    mode = "dry_run" if args.dry_run else "real"
    output_dir = args.output_dir / f"{timestamp}_{mode}"
    rows = []

    for idx, question in enumerate(questions, 1):
        query = str(question.get("query") or "").strip()
        if not query:
            continue
        print(f"[{idx}/{len(questions)}] {question.get('id')}: {query}", flush=True)
        qa_args: SimpleNamespace = default_namespace(
            query=query,
            keywords=question.get("keywords") or [],
            dry_run=args.dry_run,
            context_k=args.context_k,
            graph_evidence_k=args.graph_evidence_k,
            retrieval_k=args.retrieval_k,
            relation_k=args.relation_k,
            relation_evidence_k=args.relation_evidence_k,
            graph_evidence_pool_k=args.graph_evidence_pool_k,
            max_chars_per_chunk=args.max_chars_per_chunk,
        )
        start = time.time()
        try:
            result = answer_query(qa_args)
            rows.append(evaluate_result(question, result, time.time() - start))
        except Exception as exc:
            rows.append(
                {
                    "id": question.get("id"),
                    "category": question.get("category"),
                    "query": query,
                    "dry_run": args.dry_run,
                    "ok": False,
                    "checks": {"error_free": False},
                    "metrics": {"elapsed_seconds": round(time.time() - start, 2)},
                    "error": str(exc),
                }
            )

    summary = summarize(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "results.jsonl", rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote: {output_dir}")
    return 0 if summary["ok"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
