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

from evaluate_qa import evaluate_result  # noqa: E402
from kgrag_answer import (  # noqa: E402
    build_prompt,
    call_openai_compatible,
    default_namespace,
    expand_keywords,
    retrieve_context,
    summarize_context,
)


INTENT_RULES = {
    "safety_boundary": (
        "治愈",
        "直接治疗",
        "推荐用药",
        "停药",
        "不用专业评估",
        "无需专业评估",
        "替代诊断",
        "确定有效",
        "高压氧",
    ),
    "diagnostic_boundary": (
        "能诊断",
        "判断是",
        "能判断",
        "就能判断",
        "是不是自闭症",
        "是不是孤独症",
        "只凭",
        "量表分数",
        "代替诊断",
    ),
    "intervention_advice": (
        "干预",
        "训练",
        "治疗",
        "aba",
        "eibi",
        "esdm",
        "家长培训",
        "融合支持",
        "感觉统合",
    ),
}

RESEARCH_ONLY_QA_USAGE = "research_context_only"


def classify_query_intent(query: str) -> dict[str, Any]:
    normalized = (query or "").strip().lower()
    matched: dict[str, list[str]] = {}
    for intent, terms in INTENT_RULES.items():
        hits = [term for term in terms if term.lower() in normalized]
        if hits:
            matched[intent] = hits
    if "safety_boundary" in matched:
        intent = "safety_boundary"
    elif "diagnostic_boundary" in matched:
        intent = "diagnostic_boundary"
    elif "intervention_advice" in matched:
        intent = "intervention_advice"
    elif normalized:
        intent = "knowledge_qa"
    else:
        intent = "unknown"
    return {
        "intent": intent,
        "matched_terms": matched,
        "requires_guardrail": intent in {
            "safety_boundary",
            "diagnostic_boundary",
            "intervention_advice",
        },
    }


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
    context = retrieve_context(
        args,
        driver=driver,
        embed_model=embed_model,
        qdrant_client=qdrant_client,
    )
    return {
        "raw_context": context,
        "summary": summarize_context(context),
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
    }


def inspect_evidence(context_summary: dict[str, Any]) -> dict[str, Any]:
    contexts = context_summary.get("contexts") or []
    relations = context_summary.get("relations") or []
    graph_counts = context_summary.get("graph_counts") or {}
    low_evidence = [
        item
        for item in contexts
        if str(item.get("evidence_level") or "").upper() in {"C", "D", "LOW"}
    ]
    research_only_relations = [
        row for row in relations if row.get("qa_usage") == RESEARCH_ONLY_QA_USAGE
    ]
    flags = {
        "has_contexts": bool(contexts),
        "has_relations": bool(relations),
        "has_graph_entities": int(graph_counts.get("entities") or 0) > 0,
        "has_low_evidence_context": bool(low_evidence),
        "has_research_only_context": bool(research_only_relations),
        "needs_more_retrieval": len(contexts) < 3 and not relations,
    }
    return {
        "flags": flags,
        "counts": {
            "contexts": len(contexts),
            "relations": len(relations),
            "low_evidence_contexts": len(low_evidence),
            "research_only_relations": len(research_only_relations),
        },
        "answer_policy": {
            "requires_guardrail": flags["has_low_evidence_context"] or flags["has_research_only_context"],
            "requires_research_boundary": flags["has_research_only_context"],
            "allow_clinical_certainty": not flags["has_low_evidence_context"]
            and not flags["has_research_only_context"],
        },
    }


def merge_answer_policy(intent: dict[str, Any], evidence_report: dict[str, Any]) -> dict[str, Any]:
    policy = dict(evidence_report.get("answer_policy") or {})
    intent_requires_guardrail = bool(intent.get("requires_guardrail"))
    policy["requires_guardrail"] = bool(policy.get("requires_guardrail")) or intent_requires_guardrail
    if (intent.get("intent") or "") in {"safety_boundary", "diagnostic_boundary"}:
        policy["allow_clinical_certainty"] = False
    evidence_report["answer_policy"] = policy
    return evidence_report


def should_run_followup_retrieval(intent: dict[str, Any], evidence_report: dict[str, Any]) -> bool:
    flags = evidence_report.get("flags") or {}
    intent_name = intent.get("intent")
    if flags.get("needs_more_retrieval"):
        return True
    if intent_name in {"diagnostic_boundary", "safety_boundary", "intervention_advice"}:
        return not flags.get("has_relations") or not flags.get("has_graph_entities")
    return False


def plan_followup_retrieval(
    query: str,
    intent: dict[str, Any],
    expansion: dict[str, Any],
    evidence_report: dict[str, Any],
) -> list[dict[str, Any]]:
    if not should_run_followup_retrieval(intent, evidence_report):
        return []

    intent_name = intent.get("intent")
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
) -> dict[str, Any]:
    policy = evidence_report.get("answer_policy") or {}
    question = {
        "id": "agent_query",
        "category": classify_query_intent(query)["intent"],
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

    started = time.time()
    intent = classify_query_intent(args.query)
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
    drafted = draft_answer_tool(args, retrieved["raw_context"])
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
    validation = validate_answer_tool(args.query, result, evidence, time.time() - workflow_start)
    result["agent"]["validation"] = validation
    if trace:
        trace.add_step("validate_answer", outputs=validation, started_at=started)

    return result
