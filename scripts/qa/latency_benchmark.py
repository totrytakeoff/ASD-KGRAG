#!/usr/bin/env python3
"""Latency and quality benchmark jobs for OpenAI-compatible QA models."""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path
from types import SimpleNamespace

from evaluate_qa import evaluate_result
from agent_tools import stream_toolized_agent_events
from kgrag_answer import default_namespace, stream_answer_query_events
from qa_profiles import apply_qa_profile


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = ROOT / "data" / "qa_benchmarks"
DEFAULT_CANDIDATE_MODELS = [
    "Qwen/Qwen3.5-27B",
    "Qwen/Qwen3.5-9B",
    "deepseek-ai/DeepSeek-V4-Flash",
    "zai-org/GLM-4.5-Air",
]


def _job_path(job_id: str) -> Path:
    return BENCHMARK_DIR / f"{job_id}.json"


def write_job(job: dict) -> None:
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    _job_path(job["job_id"]).write_text(
        json.dumps(job, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_job(job_id: str) -> dict | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_jobs(limit: int = 30) -> list[dict]:
    if not BENCHMARK_DIR.exists():
        return []
    jobs = []
    for path in sorted(BENCHMARK_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return jobs


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return round(ordered[index], 3)


def run_one(
    *,
    question: dict,
    model_cfg: dict,
    profile: str,
    pipeline: str,
    driver,
    embed_model,
    qdrant_client,
) -> dict:
    args: SimpleNamespace = default_namespace(
        query=str(question.get("query") or ""),
        keywords=question.get("keywords") or [],
        dry_run=False,
    )
    args.llm_model = model_cfg["name"]
    args.llm_base_url = model_cfg["base_url"]
    args.llm_api_key = model_cfg["api_key"]
    args.llm_timeout = float(model_cfg.get("timeout") or 90)
    args.llm_max_retries = int(model_cfg.get("max_retries") or 0)
    args.disable_retrieval_cache = True
    apply_qa_profile(args, profile)

    started_at = time.perf_counter()
    context = {}
    answer_parts = []
    timing = {}
    status = "error"
    error = None
    event_source = stream_toolized_agent_events if pipeline == "agent" else stream_answer_query_events
    for event in event_source(args, driver=driver, embed_model=embed_model, qdrant_client=qdrant_client):
        if event.get("type") == "context":
            context = event.get("context") or {}
        elif event.get("type") == "token":
            answer_parts.append(event.get("text") or "")
        elif event.get("type") in {"done", "degraded"}:
            status = event["type"]
            timing = event.get("timing") or {}
            if event.get("answer"):
                answer_parts = [event["answer"]]
            error = event.get("detail")
    elapsed = time.perf_counter() - started_at
    result = {
        "query": args.query,
        "dry_run": False,
        "context": context,
        "answer": "".join(answer_parts),
        "degraded": status == "degraded",
    }
    evaluated = evaluate_result(question, result, elapsed)
    generated_answer_ok = status == "done" and bool(result["answer"].strip())
    quality_checks = {"generated_answer": generated_answer_ok, **(evaluated.get("checks") or {})}
    return {
        "question_id": question.get("id"),
        "query": args.query,
        "model": model_cfg["name"],
        "profile": profile,
        "pipeline": pipeline,
        "status": status,
        "error": error,
        "timing": timing,
        "answer_chars": len(result["answer"]),
        "quality": {
            "ok": bool(evaluated.get("ok")) and generated_answer_ok,
            "checks": quality_checks,
        },
    }


def summarize_rows(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["model"], row["profile"], row["pipeline"]), []).append(row)
    summaries = []
    for (model, profile, pipeline), items in groups.items():
        ttft = [float(row["timing"]["first_token_sec"]) for row in items if row.get("timing", {}).get("first_token_sec") is not None]
        totals = [float(row["timing"]["api_total_sec"]) for row in items if row.get("timing", {}).get("api_total_sec") is not None]
        summaries.append(
            {
                "model": model,
                "profile": profile,
                "pipeline": pipeline,
                "runs": len(items),
                "successes": sum(1 for row in items if row["status"] == "done"),
                "degraded": sum(1 for row in items if row["status"] == "degraded"),
                "quality_passes": sum(1 for row in items if row["quality"]["ok"]),
                "ttft_p50": round(statistics.median(ttft), 3) if ttft else None,
                "ttft_p95": percentile(ttft, 0.95),
                "total_p50": round(statistics.median(totals), 3) if totals else None,
                "total_p95": percentile(totals, 0.95),
            }
        )
    return sorted(summaries, key=lambda item: (item["profile"], item["pipeline"], item["ttft_p50"] or 10**9))


def agent_gate(summary: list[dict]) -> list[dict]:
    by_key = {(item["model"], item["profile"], item["pipeline"]): item for item in summary}
    gates = []
    for model, profile, pipeline in list(by_key):
        if pipeline != "agent":
            continue
        agent = by_key[(model, profile, "agent")]
        standard = by_key.get((model, profile, "standard"))
        if not standard:
            continue
        standard_total = standard.get("total_p50") or 0
        agent_total = agent.get("total_p50") or 0
        overhead = ((agent_total - standard_total) / standard_total) if standard_total else None
        passed = (
            agent["successes"] >= standard["successes"]
            and agent["quality_passes"] >= standard["quality_passes"]
            and overhead is not None
            and overhead <= 0.2
        )
        gates.append(
            {
                "model": model,
                "profile": profile,
                "passed": passed,
                "latency_overhead_rate": round(overhead, 4) if overhead is not None else None,
            }
        )
    return gates


def run_benchmark_job(
    *,
    job: dict,
    questions: list[dict],
    model_names: list[str],
    profiles: list[str],
    pipelines: list[str],
    repeats: int,
    active_model: dict,
    driver,
    embed_model,
    qdrant_client,
) -> None:
    job["status"] = "running"
    job["started_at"] = time.time()
    write_job(job)
    rows = []
    try:
        for model_name in model_names:
            model_cfg = {**active_model, "name": model_name}
            for profile in profiles:
                for pipeline in pipelines:
                    for _repeat in range(repeats):
                        for question in questions:
                            row = run_one(
                                question=question,
                                model_cfg=model_cfg,
                                profile=profile,
                                pipeline=pipeline,
                                driver=driver,
                                embed_model=embed_model,
                                qdrant_client=qdrant_client,
                            )
                            rows.append(row)
                            job["rows"] = rows
                            job["completed_runs"] = len(rows)
                            write_job(job)
        job["status"] = "completed"
        job["rows"] = rows
        job["summary"] = summarize_rows(rows)
        job["agent_gate"] = agent_gate(job["summary"])
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["rows"] = rows
        job["summary"] = summarize_rows(rows)
        job["agent_gate"] = agent_gate(job["summary"])
    finally:
        job["finished_at"] = time.time()
        write_job(job)
