#!/usr/bin/env python3
"""Batch retrieval diagnostics for natural-query KGRAG evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from evaluate_qa import (  # noqa: E402
    DEFAULT_INPUT,
    evaluate_result,
    open_shared_resources,
    read_jsonl,
    write_jsonl,
)
from kgrag_answer import (  # noqa: E402
    default_namespace,
    load_dotenv,
    retrieve_context,
    summarize_context,
)
from qa_profiles import DEFAULT_QA_PROFILE, apply_qa_profile  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "data" / "retrieval_diagnostics"
ACTIONABLE_QUALITY_FLAGS = {
    "alias_type_conflict",
    "same_name_duplicate",
    "isolated_entity",
    "single_chunk_entity",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose KGRAG retrieval on the QA evaluation set.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--profile", choices=["fast", "balanced", "deep"], default=DEFAULT_QA_PROFILE)
    parser.add_argument(
        "--use-question-keywords",
        action="store_true",
        help="Use curated keywords instead of evaluating natural-query keyword extraction.",
    )
    return parser.parse_args()


def select_questions(args: argparse.Namespace) -> list[dict]:
    questions = read_jsonl(args.input)
    if args.ids:
        wanted = set(args.ids)
        questions = [question for question in questions if question.get("id") in wanted]
    if args.limit > 0:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit("No questions selected.")
    return questions


def compact_entity(entity: dict) -> dict:
    return {
        key: entity.get(key)
        for key in (
            "entity_id",
            "name",
            "type",
            "matched_keywords",
            "exact_match",
            "source_chunk_count",
            "source_doc_count",
            "quality_flags",
            "is_isolated",
        )
    }


def compact_relation(relation: dict) -> dict:
    return {
        key: relation.get(key)
        for key in (
            "relation_id",
            "source",
            "source_type",
            "relation",
            "target",
            "target_type",
            "support_count",
            "confidence",
            "qa_usage",
        )
    }


def compact_chunk(chunk: dict) -> dict:
    return {
        key: chunk.get(key)
        for key in (
            "chunk_id",
            "doc_id",
            "title",
            "year",
            "evidence_level",
            "source_type",
            "retrieval",
            "score",
            "in_graph",
            "merged_score",
            "vector_query",
            "vector_query_rank",
            "relation_id",
            "entity_id",
        )
    }


def diagnose_one(question: dict, args: argparse.Namespace, driver, embed_model, qdrant_client) -> dict:
    qa_args = default_namespace(
        query=str(question.get("query") or "").strip(),
        keywords=(question.get("keywords") or []) if args.use_question_keywords else [],
        dry_run=True,
        include_diagnostics=True,
        disable_retrieval_cache=True,
    )
    apply_qa_profile(qa_args, args.profile)
    started = time.perf_counter()
    context = retrieve_context(
        qa_args,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
    )
    elapsed = time.perf_counter() - started
    context_summary = summarize_context(context)
    evaluation_context = {
        **context_summary,
        "contexts": context.get("contexts") or [],
    }
    evaluated = evaluate_result(
        question,
        {"query": qa_args.query, "dry_run": True, "context": evaluation_context},
        elapsed,
    )
    diagnostics = context.get("diagnostics") or {}
    matched_entities = diagnostics.get("matched_entities") or []
    relation_entities = diagnostics.get("relation_entities") or []
    failures = [name for name, passed in evaluated["checks"].items() if not passed]
    return {
        "id": question.get("id"),
        "category": question.get("category"),
        "query": qa_args.query,
        "expected_terms": question.get("expect_graph_terms") or [],
        "profile": args.profile,
        "used_question_keywords": args.use_question_keywords,
        "input_keywords": diagnostics.get("input_keywords") or [],
        "expanded_keywords": context.get("keywords") or [],
        "specific_keywords": diagnostics.get("specific_keywords") or [],
        "vector_queries": context.get("vector_queries") or [],
        "graph_counts": context_summary.get("graph_counts") or {},
        "matched_entities": [compact_entity(entity) for entity in matched_entities],
        "relation_entity_ids": [entity.get("entity_id") for entity in relation_entities],
        "relations": [compact_relation(relation) for relation in (context.get("relations") or [])[:20]],
        "vector_hits": [compact_chunk(chunk) for chunk in (diagnostics.get("vector_hits") or [])[:10]],
        "graph_evidence_pool": [
            compact_chunk(chunk) for chunk in (diagnostics.get("graph_evidence_pool") or [])[:10]
        ],
        "final_contexts": [compact_chunk(chunk) for chunk in (context.get("contexts") or [])],
        "checks": evaluated.get("checks") or {},
        "metrics": evaluated.get("metrics") or {},
        "failures": failures,
    }


def summarize(rows: list[dict]) -> dict:
    check_failures = Counter()
    retrieval_modes = Counter()
    quality_flags = Counter()
    by_category: dict[str, dict[str, int]] = {}
    governance_candidates: dict[str, dict] = {}

    for row in rows:
        failed = bool(row["failures"])
        category = row.get("category") or "uncategorized"
        category_summary = by_category.setdefault(category, {"total": 0, "failed": 0})
        category_summary["total"] += 1
        category_summary["failed"] += int(failed)
        check_failures.update(row["failures"])
        retrieval_modes.update(
            context.get("retrieval") or "unknown" for context in row.get("final_contexts") or []
        )
        for entity in row.get("matched_entities") or []:
            entity_flags = entity.get("quality_flags") or []
            quality_flags.update(entity_flags)
            low_support = int(entity.get("source_chunk_count") or 0) <= 1
            actionable_flag = any(
                flag in ACTIONABLE_QUALITY_FLAGS or flag.startswith("assessment_tool_category:")
                for flag in entity_flags
            )
            if not (entity.get("is_isolated") or low_support or actionable_flag):
                continue
            entity_id = str(entity.get("entity_id") or entity.get("name") or "unknown")
            candidate = governance_candidates.setdefault(
                entity_id,
                {**entity, "query_count": 0, "question_ids": []},
            )
            candidate["query_count"] += 1
            candidate["question_ids"].append(row.get("id"))

    failed_rows = [row for row in rows if row["failures"]]
    candidates = sorted(
        governance_candidates.values(),
        key=lambda item: (-int(item["query_count"]), int(item.get("source_chunk_count") or 0)),
    )
    return {
        "total": len(rows),
        "passed": len(rows) - len(failed_rows),
        "failed": len(failed_rows),
        "pass_rate": round((len(rows) - len(failed_rows)) / len(rows), 4) if rows else 0.0,
        "check_failures": dict(check_failures),
        "by_category": by_category,
        "retrieval_modes": dict(retrieval_modes),
        "quality_flags": dict(quality_flags),
        "failure_ids": [row.get("id") for row in failed_rows],
        "governance_candidates": candidates[:100],
    }


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    questions = select_questions(args)
    rows = []
    with ExitStack() as stack:
        try:
            driver, embed_model, qdrant_client = open_shared_resources(stack)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from None
        for index, question in enumerate(questions, 1):
            print(f"[{index}/{len(questions)}] {question.get('id')}", flush=True)
            rows.append(diagnose_one(question, args, driver, embed_model, qdrant_client))

    mode = "curated_keywords" if args.use_question_keywords else "natural_query"
    output_dir = args.output_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_{args.profile}_{mode}"
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "results.jsonl", rows)
    summary = summarize(rows)
    summary["config"] = {
        "profile": args.profile,
        "use_question_keywords": args.use_question_keywords,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote: {output_dir}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
