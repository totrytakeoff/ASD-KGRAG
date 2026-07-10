#!/usr/bin/env python3
"""Named QA profiles shared by the API, agent, and benchmark tooling."""
from __future__ import annotations

from types import SimpleNamespace


QA_PROFILES = {
    "fast": {
        "context_k": 2,
        "graph_evidence_k": 1,
        "max_chars_per_chunk": 400,
        "llm_max_tokens": 500,
    },
    "balanced": {
        "context_k": 4,
        "graph_evidence_k": 2,
        "max_chars_per_chunk": 600,
        "llm_max_tokens": 800,
    },
    "deep": {
        "context_k": 6,
        "graph_evidence_k": 4,
        "max_chars_per_chunk": 900,
        "llm_max_tokens": 1200,
    },
}

DEFAULT_QA_PROFILE = "balanced"


def apply_qa_profile(
    ns: SimpleNamespace,
    profile: str = DEFAULT_QA_PROFILE,
    **overrides,
) -> SimpleNamespace:
    if profile not in QA_PROFILES:
        raise ValueError(f"Unknown QA profile: {profile}")
    ns.qa_profile = profile
    for key, value in QA_PROFILES[profile].items():
        setattr(ns, key, value)
    for key, value in overrides.items():
        if value is not None:
            setattr(ns, key, value)
    return ns
