#!/usr/bin/env python3
"""Deterministic query routing for controlled KGRAG agent workflows."""
from __future__ import annotations

from typing import Any


ROUTE_RULES = {
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
        "能否推荐",
    ),
    "diagnostic_boundary": (
        "能诊断",
        "直接诊断",
        "判断是",
        "能判断",
        "就能判断",
        "是不是自闭症",
        "是不是孤独症",
        "只凭",
        "量表分数",
        "代替诊断",
        "替代诊断",
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
        "音乐治疗",
    ),
    "risk_info": (
        "风险",
        "相关吗",
        "早产",
        "围产",
        "围生",
        "遗传",
        "家族史",
        "父母年龄",
    ),
    "assessment_info": (
        "ados",
        "ados-2",
        "adi-r",
        "m-chat",
        "m-chat-r/f",
        "cars",
        "srs",
        "scq",
        "aq",
        "atec",
        "量表",
        "问卷",
        "筛查",
        "评估工具",
    ),
}

ROUTE_PRIORITY = [
    "safety_boundary",
    "diagnostic_boundary",
    "intervention_advice",
    "risk_info",
    "assessment_info",
]

ROUTE_RETRIEVAL_FOCUS = {
    "safety_boundary": ["safety", "evidence_boundary", "clinical_guardrail"],
    "diagnostic_boundary": ["diagnosis", "assessment", "professional_evaluation"],
    "intervention_advice": ["intervention", "evidence_boundary", "clinical_guardrail"],
    "risk_info": ["risk", "association", "evidence_boundary"],
    "assessment_info": ["assessment", "screening", "diagnosis_boundary"],
    "knowledge_qa": ["knowledge", "graph_evidence"],
    "unknown": [],
}

GUARDRAIL_ROUTES = {
    "safety_boundary",
    "diagnostic_boundary",
    "intervention_advice",
    "risk_info",
}

FOLLOWUP_ROUTES = {
    "safety_boundary",
    "diagnostic_boundary",
    "intervention_advice",
}


def route_query(query: str) -> dict[str, Any]:
    normalized = (query or "").strip().lower()
    matched: dict[str, list[str]] = {}
    for route, terms in ROUTE_RULES.items():
        hits = [term for term in terms if term.lower() in normalized]
        if hits:
            matched[route] = hits

    route = "unknown"
    if normalized:
        route = "knowledge_qa"
    for candidate in ROUTE_PRIORITY:
        if candidate in matched:
            route = candidate
            break

    return {
        "route": route,
        "intent": route,
        "matched_terms": matched,
        "requires_guardrail": route in GUARDRAIL_ROUTES,
        "requires_followup_retrieval": route in FOLLOWUP_ROUTES,
        "retrieval_focus": ROUTE_RETRIEVAL_FOCUS.get(route, []),
    }


def classify_query_intent(query: str) -> dict[str, Any]:
    """Backward-compatible alias for the initial agent tool API."""
    return route_query(query)
