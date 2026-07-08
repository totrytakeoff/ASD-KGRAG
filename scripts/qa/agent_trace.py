#!/usr/bin/env python3
"""Structured trace helpers for controlled KGRAG agent workflows."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
import uuid
from pathlib import Path
from typing import Any


def _safe_payload(payload: Any) -> Any:
    """Keep trace JSON readable without losing the useful structure."""
    if isinstance(payload, dict):
        return {str(key): _safe_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_safe_payload(value) for value in payload]
    if isinstance(payload, tuple):
        return [_safe_payload(value) for value in payload]
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    return repr(payload)


@dataclass
class AgentTrace:
    query: str
    workflow: str = "toolized_kgrag_v1"
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.time)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add_step(
        self,
        name: str,
        *,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        started_at: float | None = None,
        error: str | None = None,
    ) -> None:
        now = time.time()
        step_started = started_at if started_at is not None else now
        row = {
            "name": name,
            "started_at": round(step_started, 6),
            "finished_at": round(now, 6),
            "elapsed_seconds": round(now - step_started, 4),
            "inputs": _safe_payload(inputs or {}),
            "outputs": _safe_payload(outputs or {}),
        }
        if error:
            row["error"] = error
        self.steps.append(row)

    def to_dict(self) -> dict[str, Any]:
        finished_at = time.time()
        return {
            "trace_id": self.trace_id,
            "workflow": self.workflow,
            "query": self.query,
            "started_at": round(self.started_at, 6),
            "finished_at": round(finished_at, 6),
            "elapsed_seconds": round(finished_at - self.started_at, 4),
            "steps": self.steps,
        }

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
