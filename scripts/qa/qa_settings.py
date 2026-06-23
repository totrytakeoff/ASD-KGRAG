#!/usr/bin/env python3
"""Read/write QA runtime settings from config/qa_settings.json.

Provides fallback to env vars and hardcoded defaults when the file
does not exist.  The file is never required — only *explicit overrides*
made through the Dashboard are stored there.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = ROOT / "config" / "qa_settings.json"

# Defaults matching those in kgrag_answer.py
DEFAULT_ACTIVE_MODEL = {
    "name": os.environ.get("LLM_MODEL") or "deepseek-ai/DeepSeek-V4-Flash",
    "base_url": os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
    "api_key": os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "",
    "timeout": int(os.environ.get("LLM_TIMEOUT_SECONDS", "90")),
    "max_tokens": int(os.environ.get("QA_LLM_MAX_TOKENS", "1200")),
    "max_retries": int(os.environ.get("LLM_MAX_RETRIES", "1")),
}

DEFAULT_EVAL_MODELS = [
    {
        "name": os.environ.get("LLM_MODEL") or DEFAULT_ACTIVE_MODEL["name"],
        "base_url": os.environ.get("LLM_BASE_URL") or DEFAULT_ACTIVE_MODEL["base_url"],
        "api_key": os.environ.get("LLM_API_KEY") or DEFAULT_ACTIVE_MODEL["api_key"],
        "timeout": DEFAULT_ACTIVE_MODEL["timeout"],
        "max_tokens": DEFAULT_ACTIVE_MODEL["max_tokens"],
        "enabled": True,
    }
]


def _read() -> dict:
    if not SETTINGS_PATH.exists():
        return {"active_model": dict(DEFAULT_ACTIVE_MODEL), "eval_models": list(DEFAULT_EVAL_MODELS)}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"active_model": dict(DEFAULT_ACTIVE_MODEL), "eval_models": list(DEFAULT_EVAL_MODELS)}


def _write(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_settings() -> dict:
    """Return the full settings dict (active_model + eval_models)."""
    data = _read()
    # Ensure keys exist
    if "active_model" not in data:
        data["active_model"] = dict(DEFAULT_ACTIVE_MODEL)
    if "eval_models" not in data:
        data["eval_models"] = list(DEFAULT_EVAL_MODELS)
    return data


def update_active_model(model: dict) -> dict:
    """Overwrite the active QA model config and persist."""
    data = _read()
    # Merge, keeping existing keys for any fields not provided
    merged = dict(data.get("active_model", DEFAULT_ACTIVE_MODEL))
    merged.update(model)
    data["active_model"] = merged
    _write(data)
    return data


def get_eval_models() -> list[dict]:
    return _read().get("eval_models", list(DEFAULT_EVAL_MODELS))


def add_eval_model(model: dict) -> list[dict]:
    data = _read()
    entry = {"enabled": True, **model}
    data.setdefault("eval_models", []).append(entry)
    _write(data)
    return data["eval_models"]


def update_eval_model(index: int, patch: dict) -> list[dict]:
    data = _read()
    models = data.setdefault("eval_models", [])
    if 0 <= index < len(models):
        models[index].update(patch)
        _write(data)
    return models


def delete_eval_model(index: int) -> list[dict]:
    data = _read()
    models = data.setdefault("eval_models", [])
    if 0 <= index < len(models):
        models.pop(index)
        _write(data)
    return models


def apply_active_model_to_ns(ns, settings: dict | None = None) -> None:
    """Mutate a SimpleNamespace QA-args with the active model overrides.

    Call this *after* ``default_namespace()`` so file-based overrides
    take precedence over env defaults.
    """
    if settings is None:
        settings = get_settings()
    am = settings.get("active_model", {})
    if am.get("name"):
        ns.llm_model = am["name"]
    if am.get("base_url"):
        ns.llm_base_url = am["base_url"]
    if am.get("api_key"):
        ns.llm_api_key = am["api_key"]
    if am.get("timeout"):
        ns.llm_timeout = float(am["timeout"])
    if am.get("max_tokens"):
        ns.llm_max_tokens = int(am["max_tokens"])
    if am.get("max_retries") is not None:
        ns.llm_max_retries = int(am["max_retries"])
