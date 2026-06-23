#!/usr/bin/env python3
"""Multi-model evaluation runner for the Dashboard CI/CD workflow.

Called programmatically by ``POST /dashboard/eval/run``.
Writes one output directory per model under ``data/qa_eval/``.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from kgrag_answer import answer_query, default_namespace
from evaluate_qa import evaluate_result, read_jsonl, summarize, write_jsonl

DEFAULT_INPUT = ROOT / "scripts" / "qa" / "eval_questions.jsonl"
OUTPUT_BASE = ROOT / "data" / "qa_eval"


def _sanitize_model_name(name: str) -> str:
    """Turn a model identifier into a filesystem-safe slug."""
    return name.replace("/", "_").replace(" ", "_").replace(":", "_")


def run_eval(
    *,
    questions: list[dict] | None = None,
    models: list[dict],
    dry_run: bool = False,
    driver=None,
    embed_model=None,
    qdrant_client=None,
) -> list[dict]:
    """Run evaluation against each enabled model and return per-model summaries.

    Returns
    -------
    list[dict]
        Each entry::

            {
                "model_name": str,
                "output_dir": str,
                "total": int,
                "ok": int,
                "ok_rate": float,
                "error": str | None,
            }
    """
    if questions is None:
        questions = read_jsonl(DEFAULT_INPUT)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results: list[dict] = []

    for model_cfg in models:
        if not model_cfg.get("enabled", True):
            continue

        model_name = model_cfg.get("name") or "unknown"
        slug = _sanitize_model_name(model_name)
        mode = "dry_run" if dry_run else "real"
        output_dir = OUTPUT_BASE / f"{timestamp}_{mode}_{slug}"
        model_label = f"[model={model_name}]"

        print(f"\n{'='*60}\n{model_label}  evaluating {len(questions)} questions\n{'='*60}", flush=True)

        rows: list[dict] = []
        failures = 0
        total = len(questions)

        for idx, question in enumerate(questions, 1):
            query = str(question.get("query") or "").strip()
            if not query:
                continue

            print(f"  [{idx}/{total}] {question.get('id')}: {query[:60]}...", flush=True)

            qa_args: SimpleNamespace = default_namespace(
                query=query,
                keywords=question.get("keywords") or [],
                dry_run=dry_run,
                context_k=6,
                graph_evidence_k=4,
                retrieval_k=20,
                relation_k=30,
                relation_evidence_k=6,
                graph_evidence_pool_k=30,
                max_chars_per_chunk=900,
            )
            # Override LLM config from model_cfg
            if model_cfg.get("name"):
                qa_args.llm_model = model_cfg["name"]
            if model_cfg.get("base_url"):
                qa_args.llm_base_url = model_cfg["base_url"]
            if model_cfg.get("api_key"):
                qa_args.llm_api_key = model_cfg["api_key"]
            if model_cfg.get("timeout"):
                qa_args.llm_timeout = float(model_cfg["timeout"])
            if model_cfg.get("max_tokens"):
                qa_args.llm_max_tokens = int(model_cfg["max_tokens"])
            if model_cfg.get("max_retries") is not None:
                qa_args.llm_max_retries = int(model_cfg["max_retries"])

            start = time.time()
            try:
                result = answer_query(
                    qa_args,
                    driver=driver,
                    embed_model=embed_model,
                    qdrant_client=qdrant_client,
                )
                rows.append(evaluate_result(question, result, time.time() - start))
            except Exception as exc:
                failures += 1
                rows.append({
                    "id": question.get("id"),
                    "category": question.get("category"),
                    "query": query,
                    "dry_run": dry_run,
                    "ok": False,
                    "checks": {"error_free": False},
                    "metrics": {"elapsed_seconds": round(time.time() - start, 2)},
                    "error": str(exc),
                })

        summary = summarize(rows)
        output_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(output_dir / "results.jsonl", rows)
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(f"  {model_label}  ok={summary['ok']}/{summary['total']}  rate={summary['ok_rate']}")
        print(f"  wrote: {output_dir}")

        results.append({
            "model_name": model_name,
            "output_dir": str(output_dir.relative_to(ROOT)),
            "total": summary["total"],
            "ok": summary["ok"],
            "ok_rate": summary["ok_rate"],
            "cat_summary": summary.get("by_category", {}),
        })

    return results
