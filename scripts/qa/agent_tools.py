#!/usr/bin/env python3
"""Toolized wrappers around the stable KGRAG QA pipeline.

This module deliberately keeps the first agentization step narrow: tools expose
the existing retrieval, prompt, generation, and validation behavior without
changing the default answer semantics.
"""
from __future__ import annotations

from contextlib import ExitStack
from copy import copy
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from agent_policy import (  # noqa: E402
    inspect_evidence,
    merge_answer_policy,
    should_run_followup_retrieval,
)
from agent_router import route_query  # noqa: E402
from evaluate_qa import evaluate_result  # noqa: E402
from kgrag_answer import (  # noqa: E402
    build_prompt,
    build_evidence_fallback,
    call_openai_compatible,
    call_openai_compatible_stream,
    default_namespace,
    expand_keywords,
    retrieve_context_cached,
    summarize_context,
)


def expand_query(query: str, keywords: list[str] | None = None) -> dict[str, Any]:
    base_keywords = list(keywords or [])
    args = default_namespace(query=query, keywords=base_keywords)
    if not base_keywords:
        # retrieve_context also computes auto keywords; for trace readability we
        # expose deterministic lexical tokens here without performing retrieval.
        from kgrag_answer import auto_keywords  # noqa: WPS433

        base_keywords = auto_keywords(query)
    expanded = expand_keywords(base_keywords)
    return {
        "query": query,
        "input_keywords": list(keywords or []),
        "keywords": base_keywords,
        "expanded_keywords": expanded,
        "retrieval_options": {
            "retrieval_k": args.retrieval_k,
            "context_k": args.context_k,
            "relation_k": args.relation_k,
            "graph_evidence_k": args.graph_evidence_k,
        },
    }


def retrieve_context_tool(
    args: SimpleNamespace,
    *,
    driver=None,
    embed_model=None,
    qdrant_client=None,
) -> dict[str, Any]:
    context, cache_hit = retrieve_context_cached(
        args,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
    )
    return {
        "raw_context": context,
        "summary": summarize_context(context),
        "cache_hit": cache_hit,
    }


def _dedupe_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        identity = tuple(row.get(key) for key in keys)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(row)
    return deduped


def merge_retrieved_contexts(primary: dict[str, Any], supplemental: list[dict[str, Any]], context_k: int) -> dict[str, Any]:
    raw_context = dict(primary["raw_context"])
    raw_supplements = [item["raw_context"] for item in supplemental]

    contexts = _dedupe_rows(
        [
            *(raw_context.get("contexts") or []),
            *[ctx for item in raw_supplements for ctx in (item.get("contexts") or [])],
        ],
        ("chunk_id",),
    )[:context_k]
    for idx, row in enumerate(contexts, 1):
        row["citation_id"] = f"C{idx}"

    relations = _dedupe_rows(
        [
            *(raw_context.get("relations") or []),
            *[rel for item in raw_supplements for rel in (item.get("relations") or [])],
        ],
        ("source", "relation", "target"),
    )
    graph = dict(raw_context.get("graph") or {})
    graph["entities"] = _dedupe_rows(
        [
            *(graph.get("entities") or []),
            *[
                entity
                for item in raw_supplements
                for entity in ((item.get("graph") or {}).get("entities") or [])
            ],
        ],
        ("entity_id",),
    )
    graph["relations"] = _dedupe_rows(
        [
            *(graph.get("relations") or []),
            *[
                rel
                for item in raw_supplements
                for rel in ((item.get("graph") or {}).get("relations") or [])
            ],
        ],
        ("src_id", "rel_type", "neighbor_id"),
    )
    graph["chunk_ids"] = list(
        dict.fromkeys(
            [
                *(graph.get("chunk_ids") or []),
                *[
                    chunk_id
                    for item in raw_supplements
                    for chunk_id in ((item.get("graph") or {}).get("chunk_ids") or [])
                ],
            ]
        )
    )

    raw_context["contexts"] = contexts
    raw_context["relations"] = relations
    raw_context["graph"] = graph
    raw_context["keywords"] = list(
        dict.fromkeys(
            [
                *(raw_context.get("keywords") or []),
                *[kw for item in raw_supplements for kw in (item.get("keywords") or [])],
            ]
        )
    )
    raw_context["vector_queries"] = list(
        dict.fromkeys(
            [
                *(raw_context.get("vector_queries") or []),
                *[query for item in raw_supplements for query in (item.get("vector_queries") or [])],
            ]
        )
    )
    return {
        "raw_context": raw_context,
        "summary": summarize_context(raw_context),
        "cache_hit": bool(primary.get("cache_hit")) and all(
            bool(item.get("cache_hit")) for item in supplemental
        ),
    }


def plan_followup_retrieval(
    query: str,
    intent: dict[str, Any],
    expansion: dict[str, Any],
    evidence_report: dict[str, Any],
) -> list[dict[str, Any]]:
    if not should_run_followup_retrieval(intent, evidence_report):
        return []

    intent_name = intent.get("route") or intent.get("intent")
    base_keywords = expansion.get("expanded_keywords") or expansion.get("keywords") or []
    if intent_name == "diagnostic_boundary":
        return [
            {
                "reason": "diagnostic boundary query needs graph-backed assessment evidence",
                "query": "ASD 诊断评估 ADOS ADI-R DSM-5 筛查 专业评估",
                "keywords": ["ASD", "孤独症", "自闭症", "ADOS", "ADI-R", "DSM-5", "诊断", "评估", "筛查"],
            }
        ]
    if intent_name == "intervention_advice":
        return [
            {
                "reason": "intervention query needs graph-backed intervention evidence",
                "query": "ASD 干预 ABA EIBI ESDM 家长培训 证据边界",
                "keywords": ["ASD", "孤独症", "自闭症", "干预", "ABA", "EIBI", "ESDM", "家长培训"],
            }
        ]
    if intent_name == "safety_boundary":
        return [
            {
                "reason": "safety boundary query needs graph-backed caution evidence",
                "query": f"{query} ASD 安全 证据边界 专业评估",
                "keywords": [*base_keywords[:8], "ASD", "孤独症", "自闭症", "安全", "证据边界", "专业评估"],
            }
        ]
    return [
        {
            "reason": "initial retrieval had insufficient graph evidence",
            "query": f"{query} ASD 图谱证据 评估 干预",
            "keywords": [*base_keywords[:8], "ASD", "孤独症", "自闭症"],
        }
    ]


def build_followup_args(args: SimpleNamespace, plan: dict[str, Any]) -> SimpleNamespace:
    followup = copy(args)
    followup.query = plan["query"]
    followup.keywords = plan.get("keywords") or []
    followup.context_k = max(args.context_k, 6)
    followup.graph_evidence_k = max(args.graph_evidence_k, 4)
    return followup


def draft_answer_tool(args: SimpleNamespace, raw_context: dict[str, Any]) -> dict[str, Any]:
    messages = build_prompt(raw_context, args.max_chars_per_chunk)
    if args.dry_run:
        return {
            "dry_run": True,
            "prompt_preview": messages[-1]["content"],
        }
    if not args.llm_api_key:
        raise RuntimeError("LLM API key is not set. Use dry_run or set LLM_API_KEY / OPENAI_API_KEY.")
    answer = call_openai_compatible(
        model=args.llm_model,
        messages=messages,
        base_url=args.llm_base_url,
        api_key=args.llm_api_key,
        timeout_seconds=args.llm_timeout,
        max_retries=args.llm_max_retries,
        max_tokens=args.llm_max_tokens,
    )
    return {
        "dry_run": False,
        "answer": answer,
    }


def validate_answer_tool(
    query: str,
    result: dict[str, Any],
    evidence_report: dict[str, Any],
    elapsed_seconds: float,
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = evidence_report.get("answer_policy") or {}
    route = route or route_query(query)
    question = {
        "id": "agent_query",
        "category": route.get("route") or route.get("intent"),
        "query": query,
        "requires_guardrail": bool(policy.get("requires_guardrail")),
        "requires_research_boundary": bool(policy.get("requires_research_boundary")),
    }
    evaluated = evaluate_result(question, result, elapsed_seconds)
    return {
        "ok": evaluated.get("ok"),
        "checks": evaluated.get("checks") or {},
        "metrics": evaluated.get("metrics") or {},
        "flags": evaluated.get("flags") or {},
    }


def redact_for_trace(payload: dict[str, Any], max_text_chars: int = 1200) -> dict[str, Any]:
    redacted = dict(payload)
    if "raw_context" in redacted:
        redacted["raw_context"] = "<omitted>"
    if "prompt_preview" in redacted:
        text = str(redacted["prompt_preview"] or "")
        redacted["prompt_preview"] = text[:max_text_chars] + ("..." if len(text) > max_text_chars else "")
    if "answer" in redacted:
        text = str(redacted["answer"] or "")
        redacted["answer"] = text[:max_text_chars] + ("..." if len(text) > max_text_chars else "")
    return redacted


def open_agent_resources(stack: ExitStack, args: SimpleNamespace):
    from neo4j import GraphDatabase
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer

    driver = GraphDatabase.driver(args.neo4j_url, auth=(args.neo4j_user, args.neo4j_pass))
    stack.callback(driver.close)
    embed_model = SentenceTransformer(args.model)
    qdrant_client = QdrantClient(url=args.qdrant_url)
    return driver, embed_model, qdrant_client


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(result)
    answer = compacted.get("answer")
    if isinstance(answer, str):
        compacted["answer_preview"] = re.sub(r"\s+", " ", answer).strip()[:240]
        compacted.pop("answer", None)
    prompt = compacted.get("prompt_preview")
    if isinstance(prompt, str):
        compacted["prompt_preview_chars"] = len(prompt)
        compacted.pop("prompt_preview", None)
    return compacted


def run_toolized_agent(
    args: SimpleNamespace,
    *,
    driver=None,
    embed_model=None,
    qdrant_client=None,
    trace=None,
) -> dict[str, Any]:
    workflow_start = time.time()
    workflow_perf_start = time.perf_counter()

    started = time.time()
    intent = route_query(args.query)
    if trace:
        trace.add_step("classify_query_intent", inputs={"query": args.query}, outputs=intent, started_at=started)

    started = time.time()
    expansion = expand_query(args.query, args.keywords)
    if trace:
        trace.add_step(
            "expand_query",
            inputs={"query": args.query, "keywords": args.keywords},
            outputs=expansion,
            started_at=started,
        )

    started = time.time()
    retrieved = retrieve_context_tool(
        args,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
    )
    if trace:
        trace.add_step(
            "retrieve_context",
            inputs={"query": args.query, "options": expansion["retrieval_options"]},
            outputs=redact_for_trace(retrieved),
            started_at=started,
        )

    started = time.time()
    evidence = inspect_evidence(retrieved["summary"])
    evidence = merge_answer_policy(intent, evidence)
    if trace:
        trace.add_step("inspect_evidence", outputs=evidence, started_at=started)

    followup_results = []
    started = time.time()
    followup_plans = plan_followup_retrieval(args.query, intent, expansion, evidence)
    if trace:
        trace.add_step(
            "plan_followup_retrieval",
            inputs={"intent": intent, "evidence_flags": evidence.get("flags")},
            outputs={"plans": followup_plans},
            started_at=started,
        )
    for idx, plan in enumerate(followup_plans[:1], 1):
        started = time.time()
        followup_args = build_followup_args(args, plan)
        followup_result = retrieve_context_tool(
            followup_args,
            driver=driver,
            embed_model=embed_model,
            qdrant_client=qdrant_client,
        )
        followup_results.append(followup_result)
        if trace:
            trace.add_step(
                f"retrieve_context_followup_{idx}",
                inputs={"plan": plan},
                outputs=redact_for_trace(followup_result),
                started_at=started,
            )

    if followup_results:
        started = time.time()
        retrieved = merge_retrieved_contexts(retrieved, followup_results, args.context_k)
        evidence = inspect_evidence(retrieved["summary"])
        evidence = merge_answer_policy(intent, evidence)
        if trace:
            trace.add_step(
                "merge_followup_evidence",
                outputs={
                    "context_count": len(retrieved["summary"].get("contexts") or []),
                    "relation_count": len(retrieved["summary"].get("relations") or []),
                    "evidence": evidence,
                },
                started_at=started,
            )

    started = time.time()
    try:
        drafted = draft_answer_tool(args, retrieved["raw_context"])
    except Exception as exc:
        drafted = {
            "dry_run": False,
            "answer": build_evidence_fallback(retrieved["summary"]),
            "degraded": True,
            "error": {"type": "llm_generation_failed", "detail": str(exc)},
        }
    result = {
        "query": args.query,
        "dry_run": bool(args.dry_run),
        "agent": {
            "workflow": "toolized_kgrag_v1",
            "intent": intent,
            "evidence": evidence,
        },
        "context": retrieved["summary"],
        **drafted,
    }
    if trace:
        trace.add_step("draft_answer", outputs=redact_for_trace(drafted), started_at=started)

    started = time.time()
    validation = validate_answer_tool(args.query, result, evidence, time.time() - workflow_start, intent)
    result["agent"]["validation"] = validation
    result["timing"] = {
        "api_total_sec": round(time.perf_counter() - workflow_perf_start, 3),
        "cache_hit": bool(retrieved.get("cache_hit")),
        "profile": getattr(args, "qa_profile", "custom"),
    }
    if trace:
        trace.add_step("validate_answer", outputs=validation, started_at=started)

    return result


def stream_toolized_agent_events(
    args: SimpleNamespace,
    *,
    driver=None,
    embed_model=None,
    qdrant_client=None,
    trace=None,
):
    workflow_start = time.perf_counter()
    yield {"type": "status", "status": "routing", "profile": getattr(args, "qa_profile", "custom")}
    intent = route_query(args.query)
    expansion = expand_query(args.query, args.keywords)

    yield {"type": "status", "status": "retrieving", "profile": getattr(args, "qa_profile", "custom")}
    retrieve_started = time.perf_counter()
    retrieved = retrieve_context_tool(
        args,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
    )
    evidence = merge_answer_policy(intent, inspect_evidence(retrieved["summary"]))
    followup_plans = plan_followup_retrieval(args.query, intent, expansion, evidence)
    if followup_plans:
        yield {"type": "status", "status": "followup_retrieval"}
        followup_result = retrieve_context_tool(
            build_followup_args(args, followup_plans[0]),
            driver=driver,
            embed_model=embed_model,
            qdrant_client=qdrant_client,
        )
        retrieved = merge_retrieved_contexts(retrieved, [followup_result], args.context_k)
        evidence = merge_answer_policy(intent, inspect_evidence(retrieved["summary"]))

    retrieve_sec = time.perf_counter() - retrieve_started
    prompt_started = time.perf_counter()
    messages = build_prompt(retrieved["raw_context"], args.max_chars_per_chunk)
    prompt_sec = time.perf_counter() - prompt_started
    timing = {
        "retrieve_sec": round(retrieve_sec, 3),
        "prompt_build_sec": round(prompt_sec, 3),
        "prompt_chars": sum(len(item.get("content", "")) for item in messages),
        "llm_sec": 0.0,
        "first_token_sec": None,
        "retry_count": 0,
        "cache_hit": bool(retrieved.get("cache_hit")),
        "profile": getattr(args, "qa_profile", "custom"),
    }
    yield {
        "type": "context",
        "query": args.query,
        "context": retrieved["summary"],
        "agent": {"workflow": "toolized_kgrag_v1", "intent": intent, "evidence": evidence},
        "timing": timing,
    }
    if args.dry_run:
        timing["api_total_sec"] = round(time.perf_counter() - workflow_start, 3)
        yield {
            "type": "done",
            "answer": "",
            "prompt_preview": messages[-1]["content"],
            "degraded": False,
            "timing": timing,
        }
        return
    yield {"type": "status", "status": "waiting_model", "timing": timing}

    if not args.llm_api_key:
        timing["api_total_sec"] = round(time.perf_counter() - workflow_start, 3)
        yield {
            "type": "degraded",
            "status": "degraded",
            "answer": build_evidence_fallback(retrieved["summary"]),
            "detail": "LLM API key is not set.",
            "degraded": True,
            "timing": timing,
        }
        return

    answer_parts = []
    first_token_at = None
    llm_started = time.perf_counter()
    try:
        for provider_event in call_openai_compatible_stream(
            model=args.llm_model,
            messages=messages,
            base_url=args.llm_base_url,
            api_key=args.llm_api_key,
            timeout_seconds=args.llm_timeout,
            max_retries=args.llm_max_retries,
            max_tokens=args.llm_max_tokens,
        ):
            if provider_event.get("type") == "retry":
                timing["retry_count"] = int(provider_event.get("attempt") or 0)
                yield {"type": "status", "status": "retrying", "timing": timing}
                continue
            text = provider_event.get("text") or ""
            if not text:
                continue
            if first_token_at is None:
                first_token_at = time.perf_counter()
                timing["first_token_sec"] = round(first_token_at - llm_started, 3)
                yield {"type": "status", "status": "generating", "timing": timing}
            answer_parts.append(text)
            yield {"type": "token", "text": text}
        if not answer_parts:
            raise RuntimeError("LLM stream completed without answer content.")
    except Exception as exc:
        timing["llm_sec"] = round(time.perf_counter() - llm_started, 3)
        timing["api_total_sec"] = round(time.perf_counter() - workflow_start, 3)
        yield {
            "type": "degraded",
            "status": "degraded",
            "answer": build_evidence_fallback(retrieved["summary"]),
            "detail": str(exc),
            "degraded": True,
            "timing": timing,
        }
        return

    timing["llm_sec"] = round(time.perf_counter() - llm_started, 3)
    timing["api_total_sec"] = round(time.perf_counter() - workflow_start, 3)
    yield {"type": "done", "answer": "".join(answer_parts), "degraded": False, "timing": timing}
