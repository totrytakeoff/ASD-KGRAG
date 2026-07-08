#!/usr/bin/env python3
"""Evidence and answer policy decisions for controlled KGRAG agents."""
from __future__ import annotations

from typing import Any


RESEARCH_ONLY_QA_USAGE = "research_context_only"

BOUNDARY_ROUTES = {
    "safety_boundary",
    "diagnostic_boundary",
}

GUARDRAIL_ROUTES = {
    "safety_boundary",
    "diagnostic_boundary",
    "intervention_advice",
    "risk_info",
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
        "answer_policy": build_answer_policy({}, flags),
    }


def build_answer_policy(route: dict[str, Any], flags: dict[str, Any]) -> dict[str, Any]:
    route_name = route.get("route") or route.get("intent") or "unknown"
    requires_guardrail = (
        bool(route.get("requires_guardrail"))
        or route_name in GUARDRAIL_ROUTES
        or bool(flags.get("has_low_evidence_context"))
        or bool(flags.get("has_research_only_context"))
    )
    requires_research_boundary = bool(flags.get("has_research_only_context"))
    allow_clinical_certainty = (
        route_name not in BOUNDARY_ROUTES
        and not flags.get("has_low_evidence_context")
        and not flags.get("has_research_only_context")
    )
    if route_name in {"intervention_advice", "risk_info"}:
        allow_clinical_certainty = False

    if route_name in BOUNDARY_ROUTES:
        answer_mode = "guardrailed_answer"
    elif requires_research_boundary:
        answer_mode = "evidence_answer_with_research_boundary"
    elif requires_guardrail:
        answer_mode = "guardrailed_answer"
    else:
        answer_mode = "evidence_answer"

    forbidden_claims = []
    if route_name == "diagnostic_boundary":
        forbidden_claims.extend(["diagnosis_from_single_symptom", "questionnaire_as_diagnosis"])
    if route_name == "safety_boundary":
        forbidden_claims.extend(["cure_claim", "direct_medication_advice", "certain_effectiveness_claim"])
    if route_name == "intervention_advice":
        forbidden_claims.extend(["one_size_fits_all_intervention", "certain_effectiveness_claim"])
    if not allow_clinical_certainty:
        forbidden_claims.append("clinical_certainty")

    return {
        "allow_answer": True,
        "answer_mode": answer_mode,
        "requires_guardrail": requires_guardrail,
        "requires_research_boundary": requires_research_boundary,
        "allow_clinical_certainty": allow_clinical_certainty,
        "forbidden_claims": sorted(set(forbidden_claims)),
    }


def merge_answer_policy(route: dict[str, Any], evidence_report: dict[str, Any]) -> dict[str, Any]:
    flags = evidence_report.get("flags") or {}
    evidence_report["answer_policy"] = build_answer_policy(route, flags)
    return evidence_report


def should_run_followup_retrieval(route: dict[str, Any], evidence_report: dict[str, Any]) -> bool:
    flags = evidence_report.get("flags") or {}
    route_name = route.get("route") or route.get("intent")
    if flags.get("needs_more_retrieval"):
        return True
    if route.get("requires_followup_retrieval"):
        return not flags.get("has_relations") or not flags.get("has_graph_entities")
    if route_name in {"diagnostic_boundary", "safety_boundary", "intervention_advice"}:
        return not flags.get("has_relations") or not flags.get("has_graph_entities")
    return False
