#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import ssl
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_existing_records(path: Path) -> tuple[set[str], dict]:
    seen_chunk_ids: set[str] = set()
    summary = {"ok": 0, "error": 0, "entity_count": 0, "relation_count": 0}
    if not path.exists():
        return seen_chunk_ids, summary

    for row in iter_jsonl(path):
        chunk_id = row.get("chunk_id")
        if chunk_id:
            seen_chunk_ids.add(chunk_id)
        status = row.get("status")
        if status == "ok":
            summary["ok"] += 1
            summary["entity_count"] += len(row.get("entities", []))
            summary["relation_count"] += len(row.get("relations", []))
        elif status == "error":
            summary["error"] += 1
    return seen_chunk_ids, summary


def normalize_text(text: str) -> str:
    return " ".join((text or "").split())


def build_messages(system_prompt: str, chunk: dict) -> list[dict]:
    payload = {
        "chunk_id": chunk.get("chunk_id"),
        "doc_id": chunk.get("doc_id"),
        "title": chunk.get("title"),
        "year": chunk.get("year"),
        "source_type": chunk.get("source_type"),
        "evidence_level": chunk.get("evidence_level"),
        "heading_path": chunk.get("heading_path"),
        "text": chunk.get("text"),
    }
    user_prompt = (
        "Extract ASD entities and relations from the following chunk. "
        "Return strict JSON with `entities` and `relations` only.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def resolve_api_config(args: argparse.Namespace) -> tuple[str, str]:
    base_url = (
        args.base_url
        or os.environ.get("LLM_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    api_key = (
        args.api_key
        or os.environ.get("LLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "API key is required for --backend openai. "
            "Use --api-key or set one of LLM_API_KEY / OPENROUTER_API_KEY / OPENAI_API_KEY."
        )
    return base_url.rstrip("/"), api_key


def resolve_model(args: argparse.Namespace) -> str:
    return args.model or os.environ.get("LLM_MODEL") or "gpt-4.1-mini"


def parse_model_json(content: str) -> dict:
    text = (content or "").strip()
    if not text:
        raise ValueError("empty model response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        fenced = "\n".join(lines).strip()
        try:
            return json.loads(fenced)
        except json.JSONDecodeError:
            text = fenced

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return json.loads(text)


def call_openai_compatible(
    model: str,
    messages: list[dict],
    base_url: str,
    api_key: str,
    site_url: str | None,
    app_name: str | None,
    timeout_seconds: float,
    max_retries: int,
    retry_sleep_seconds: float,
    max_tokens: int,
    response_format: str,
) -> dict:
    normalized_base = base_url.rstrip("/")
    if normalized_base.endswith("/chat/completions"):
        chat_url = normalized_base
    else:
        chat_url = urllib.parse.urljoin(f"{normalized_base}/", "chat/completions")

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0,
    }
    if response_format == "json_object":
        body["response_format"] = {"type": "json_object"}
    if max_tokens > 0:
        body["max_tokens"] = max_tokens
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    request_data = json.dumps(body).encode("utf-8")
    attempt = 0
    while True:
        req = urllib.request.Request(
            chat_url,
            data=request_data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            retriable = exc.code in {429, 500, 502, 503, 504}
            if retriable and attempt < max_retries:
                time.sleep(retry_sleep_seconds * (attempt + 1))
                attempt += 1
                continue
            raise RuntimeError(f"OpenAI-compatible API error: {exc.code} {detail}") from exc
        except (
            TimeoutError,
            socket.timeout,
            ConnectionError,
            ConnectionResetError,
            http.client.HTTPException,
            ssl.SSLError,
            urllib.error.URLError,
        ) as exc:
            if attempt < max_retries:
                time.sleep(retry_sleep_seconds * (attempt + 1))
                attempt += 1
                continue
            raise RuntimeError(f"OpenAI-compatible API network error: {exc}") from exc
    content = payload["choices"][0]["message"]["content"]
    return parse_model_json(content)


def validate_record(record: dict, schema: dict) -> tuple[list[dict], list[dict], list[str]]:
    entity_types = set(schema.get("entity_types", []))
    relation_types = set(schema.get("relation_types", []))
    entities = []
    relations = []
    warnings: list[str] = []
    entity_by_id: dict[str, dict] = {}

    def looks_like_assessment_tool(name: str) -> bool:
        n = normalize_text(name).lower()
        algorithm_markers = (
            "machine learning",
            "artificial intelligence",
            "support vector",
            "random forest",
            "deep learning",
            "neural network",
            "svm",
            "svr",
            "机器学习",
            "人工智能",
            "支持向量",
            "算法",
            "分类器",
            "模型",
        )
        if any(marker in n for marker in algorithm_markers):
            return False
        tool_markers = (
            "量表",
            "问卷",
            "访谈",
            "观察表",
            "记录表",
            "筛查工具",
            "诊断工具",
            "诊断标准",
            "评估工具",
            "评估表",
            "检查表",
            "scale",
            "questionnaire",
            "inventory",
            "checklist",
            "interview",
            "schedule",
            "assessment",
            "screen",
        )
        return any(marker in n for marker in tool_markers)

    def looks_like_task(name: str) -> bool:
        n = normalize_text(name).lower()
        task_markers = (
            "任务",
            "范式",
            "paradigm",
            "task",
        )
        return any(marker in n for marker in task_markers)

    def normalize_entity_type(name: str, entity_type: str) -> str:
        n = normalize_text(name).lower()
        algorithm_markers = (
            "machine learning",
            "artificial intelligence",
            "support vector",
            "random forest",
            "deep learning",
            "neural network",
            "svm",
            "svr",
            "机器学习",
            "人工智能",
            "支持向量",
            "算法",
            "分类器",
            "模型",
        )
        if entity_type == "AssessmentTool" and any(marker in n for marker in algorithm_markers):
            return "Mechanism"
        if looks_like_task(name) and not looks_like_assessment_tool(name) and entity_type != "Intervention":
            return "Task"
        if entity_type == "AssessmentTool" or looks_like_assessment_tool(name):
            return "AssessmentTool"
        if any(key in n for key in ["asd", "autism", "autistic", "自闭症", "孤独症", "谱系障碍"]):
            return "Condition"
        if any(key in n for key in ["任务", "paradigm", "task", "test"]) and entity_type not in {"AssessmentTool", "Intervention"}:
            return "Task"
        return entity_type

    allowed_pairs = {
        "MEASURED_BY": ({"Condition", "Symptom", "Task", "Mechanism", "Comorbidity", "Claim"}, {"AssessmentTool"}),
        "INDICATED_FOR": ({"Intervention"}, {"Condition", "Symptom", "Comorbidity"}),
        "NOT_INDICATED_FOR": ({"Intervention"}, {"Condition", "Symptom", "Comorbidity"}),
        "SUITABLE_AGE": ({"Intervention", "Condition"}, {"AgeStage"}),
        "SUITABLE_SETTING": ({"Intervention"}, {"Setting"}),
        "HAS_RISK": ({"Intervention"}, {"Risk"}),
        "COMORBID_WITH": ({"Condition", "Comorbidity"}, {"Condition", "Comorbidity"}),
        "SUPPORTED_BY": ({"Claim"}, {"Evidence"}),
    }

    condition_measure_verbs = (
        "diagnos",
        "screen",
        "assess",
        "measure",
        "evaluate",
        "identify",
        "诊断",
        "筛查",
        "评估",
        "测量",
        "识别",
        "检出",
    )
    condition_measure_context_terms = (
        "asd",
        "autism",
        "自闭症",
        "孤独症",
        "谱系障碍",
        "诊断",
        "筛查",
        "量表",
        "标准",
        "访谈",
        "观察",
        "diagnostic",
        "diagnosis",
        "screening",
        "assessment",
        "scale",
        "interview",
        "observation",
    )
    study_measure_verbs = (
        "研究表明",
        "研究发现",
        "显示",
        "提示",
        "发现",
        "通过",
        "使用",
        "采用",
        "measured by",
        "measured with",
        "assessed by",
        "assessed with",
        "using",
        "used",
        "found",
        "showed",
        "demonstrated",
    )
    age_evidence_markers = (
        "岁",
        "year",
        "years",
        "month",
        "儿童",
        "青少年",
        "幼儿",
        "adolescent",
        "preschool",
        "school-age",
        "adult",
    )
    weak_summary_markers = (
        "梳理了",
        "综述",
        "参考价值",
        "能够反映",
        "可反映",
        "研究成果",
        "provide reference",
        "reviewed",
        "overview",
    )

    def aliases(entity: dict) -> list[str]:
        vals = [entity.get("name", "")]
        vals.extend(entity.get("synonyms", []) or [])
        out = []
        for val in vals:
            norm = normalize_text(val).lower()
            if norm:
                out.append(norm)
        return out

    def evidence_mentions(entity: dict, evidence_text: str) -> bool:
        hay = normalize_text(evidence_text).lower()
        return any(alias in hay for alias in aliases(entity))

    def looks_like_weak_title(evidence_text: str) -> bool:
        txt = normalize_text(evidence_text)
        if len(txt) <= 18:
            return True
        punct = set("。！？!?；;:：,.，")
        return not any(ch in punct for ch in txt)

    def is_condition_tool_snippet(src: dict, dst: dict, evidence_text: str) -> bool:
        hay = normalize_text(evidence_text).lower()
        if src.get("type") != "Condition" or dst.get("type") != "AssessmentTool":
            return False
        if len(hay) < 20:
            return False
        if not evidence_mentions(dst, evidence_text):
            return False
        return any(marker in hay for marker in condition_measure_context_terms)

    def is_generic_assessment_tool(name: str) -> bool:
        n = normalize_text(name).lower()
        generic_terms = (
            "技术",
            "方法",
            "工具",
            "影像学技术",
            "神经影像学技术",
            "神经电生理技术",
            "影像学方法",
            "评估方法",
            "technique",
            "technology",
            "method",
            "approach",
        )
        specific_markers = (
            "eeg",
            "erp",
            "fmri",
            "meg",
            "mri",
            "pet",
            "spect",
            "ados",
            "adi",
            "m-chat",
            "vb-mapp",
            "abc",
            "cars",
        )
        if any(marker in n for marker in specific_markers):
            return False
        return any(term in n for term in generic_terms)

    def is_research_modality_tool(name: str) -> bool:
        n = normalize_text(name).lower()
        research_markers = (
            "mri",
            "fmri",
            "structural mri",
            "functional mri",
            "diffusion mri",
            "dti",
            "eeg",
            "erp",
            "meg",
            "eye-tracking",
            "earlipoint",
            "touchscreen",
            "弥散张量成像",
            "脑电",
            "眼动",
            "磁共振",
            "功能磁共振",
            "结构磁共振",
            "脑磁图",
            "事件相关电位",
        )
        screening_markers = (
            "ados",
            "adi-r",
            "adi",
            "m-chat",
            "chat",
            "cars",
            "abc",
            "量表",
            "问卷",
            "访谈",
            "观察表",
            "筛查工具",
            "诊断工具",
        )
        if any(marker in n for marker in screening_markers):
            return False
        return any(marker in n for marker in research_markers)

    def is_algorithmic_tool(name: str) -> bool:
        n = normalize_text(name).lower()
        algorithm_markers = (
            "machine learning",
            "artificial intelligence",
            "support vector",
            "random forest",
            "deep learning",
            "neural network",
            "svm",
            "svr",
            "机器学习",
            "人工智能",
            "支持向量",
            "算法",
            "分类器",
            "模型",
        )
        return any(marker in n for marker in algorithm_markers)

    def has_clinical_measure_signal(evidence_text: str) -> bool:
        hay = normalize_text(evidence_text).lower()
        markers = (
            "diagnos",
            "screen",
            "detect",
            "identify",
            "sensitivity",
            "specificity",
            "approved",
            "fda",
            "diagnostic tool",
            "screening tool",
            "诊断",
            "筛查",
            "检出",
            "识别",
            "敏感性",
            "特异性",
            "批准",
            "获批",
        )
        return any(marker in hay for marker in markers)

    def has_strong_clinical_performance_signal(evidence_text: str) -> bool:
        hay = normalize_text(evidence_text).lower()
        markers = (
            "sensitivity",
            "specificity",
            "accuracy",
            "precision",
            "auc",
            "approved",
            "fda",
            "diagnostic tool",
            "screening tool",
            "敏感性",
            "特异性",
            "准确率",
            "正确率",
            "精确率",
            "auc",
            "批准",
            "获批",
        )
        return any(marker in hay for marker in markers)

    for entity in record.get("entities", []):
        entity["type"] = normalize_entity_type(entity.get("name", ""), entity.get("type"))
        if entity.get("type") not in entity_types:
            warnings.append(f"invalid_entity_type:{entity.get('type')}:{entity.get('name')}")
            continue
        if entity.get("type") == "AssessmentTool" and is_generic_assessment_tool(entity.get("name", "")):
            warnings.append(f"generic_assessment_tool:{entity.get('name')}")
            continue
        entity.setdefault("description", "")
        entity.setdefault("synonyms", [])
        entities.append(entity)
        entity_by_id[entity.get("entity_id")] = entity

    valid_ids = {entity.get("entity_id") for entity in entities}
    for relation in record.get("relations", []):
        if relation.get("relation_type") not in relation_types:
            warnings.append(f"invalid_relation_type:{relation.get('relation_type')}")
            continue
        if relation.get("src_entity_id") not in valid_ids or relation.get("dst_entity_id") not in valid_ids:
            warnings.append(f"orphan_relation:{relation.get('relation_id')}")
            continue
        confidence = relation.get("confidence", 0)
        try:
            relation["confidence"] = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            relation["confidence"] = 0.0

        src = entity_by_id.get(relation.get("src_entity_id"))
        dst = entity_by_id.get(relation.get("dst_entity_id"))
        type_rule = allowed_pairs.get(relation.get("relation_type"))
        if src is None or dst is None or type_rule is None:
            warnings.append(f"missing_relation_context:{relation.get('relation_id')}")
            continue
        allowed_src, allowed_dst = type_rule
        if src.get("type") not in allowed_src or dst.get("type") not in allowed_dst:
            warnings.append(
                f"illegal_relation_pair:{relation.get('relation_type')}:{src.get('type')}->{dst.get('type')}"
            )
            continue

        evidence_text = relation.get("evidence_text", "") or ""
        if looks_like_weak_title(evidence_text) and not (
            relation.get("relation_type") == "MEASURED_BY"
            and is_condition_tool_snippet(src, dst, evidence_text)
            and (
                not is_research_modality_tool(dst.get("name", ""))
                or has_strong_clinical_performance_signal(evidence_text)
            )
        ):
            warnings.append(f"weak_evidence_text:{relation.get('relation_id')}")
            continue

        if relation.get("relation_type") == "MEASURED_BY":
            hay = normalize_text(evidence_text).lower()
            if any(marker in hay for marker in weak_summary_markers):
                warnings.append(f"summary_style_measurement:{relation.get('relation_id')}")
                continue
            if is_algorithmic_tool(dst.get("name", "")):
                warnings.append(f"algorithmic_tool_not_assessment:{relation.get('relation_id')}")
                continue
            if not evidence_mentions(dst, evidence_text):
                warnings.append(f"tool_not_mentioned:{relation.get('relation_id')}")
                continue
            src_type = src.get("type")
            if src_type in {"Task", "Symptom", "Mechanism", "Comorbidity", "Claim"} and not evidence_mentions(src, evidence_text):
                warnings.append(f"source_not_mentioned:{relation.get('relation_id')}")
                continue
            if src_type == "Condition":
                has_measure_trigger = any(marker in hay for marker in condition_measure_verbs)
                has_condition_context = any(marker in hay for marker in condition_measure_context_terms)
                if not has_measure_trigger and not has_condition_context:
                    warnings.append(f"condition_measure_without_trigger:{relation.get('relation_id')}")
                    continue
                if is_research_modality_tool(dst.get("name", "")) and not has_strong_clinical_performance_signal(evidence_text):
                    warnings.append(f"research_modality_without_clinical_signal:{relation.get('relation_id')}")
                    continue
            else:
                if not any(marker in hay for marker in study_measure_verbs):
                    warnings.append(f"measurement_without_study_trigger:{relation.get('relation_id')}")
                    continue

        if relation.get("relation_type") == "SUITABLE_AGE":
            hay = normalize_text(evidence_text).lower()
            if not evidence_mentions(dst, evidence_text):
                warnings.append(f"age_not_mentioned:{relation.get('relation_id')}")
                continue
            if not any(marker in hay for marker in age_evidence_markers):
                warnings.append(f"weak_age_evidence:{relation.get('relation_id')}")
                continue
        relations.append(relation)

    return entities, relations, warnings


def build_stub_record(chunk: dict) -> dict:
    return {"entities": [], "relations": []}


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract ASD entities and relations from chunks")
    ap.add_argument("--input", default="data/processed/chunks_full/chunks.jsonl")
    ap.add_argument("--output", default="data/processed/extraction_full")
    ap.add_argument("--schema", default="scripts/extraction/entity_relation_schema.json")
    ap.add_argument("--system-prompt", default="scripts/extraction/entity_relation_system_prompt.txt")
    ap.add_argument("--backend", choices=["stub", "openai"], default="stub")
    ap.add_argument("--model", default="")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--site-url", default="")
    ap.add_argument("--app-name", default="ASD-KGRAG")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start-index", type=int, default=0)
    ap.add_argument("--sleep-seconds", type=float, default=0.0)
    ap.add_argument("--request-timeout", type=float, default=120.0)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--retry-sleep-seconds", type=float, default=3.0)
    ap.add_argument("--max-tokens", type=int, default=int(os.environ.get("LLM_MAX_TOKENS", "0") or "0"))
    ap.add_argument(
        "--response-format",
        choices=["json_object", "none"],
        default=os.environ.get("LLM_RESPONSE_FORMAT") or "json_object",
    )
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--summary-every", type=int, default=50)
    args = ap.parse_args()

    chunks_path = Path(args.input).resolve()
    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    schema = load_json(Path(args.schema).resolve())
    system_prompt = Path(args.system_prompt).resolve().read_text(encoding="utf-8")

    rows = list(iter_jsonl(chunks_path))
    if args.start_index > 0:
        rows = rows[args.start_index :]
    if args.limit > 0:
        rows = rows[: args.limit]

    out_jsonl = out_root / "chunk_extractions.jsonl"
    base_url = ""
    api_key = ""
    model = ""
    if args.backend == "openai":
        base_url, api_key = resolve_api_config(args)
        model = resolve_model(args)

    existing_seen: set[str] = set()
    existing_summary = {"ok": 0, "error": 0, "entity_count": 0, "relation_count": 0}
    if args.resume:
        existing_seen, existing_summary = load_existing_records(out_jsonl)
        rows = [row for row in rows if row.get("chunk_id") not in existing_seen]

    summary = {
        "total_chunks": len(rows) + len(existing_seen),
        "pending_chunks": len(rows),
        "backend": args.backend,
        "model": model if args.backend == "openai" else None,
        "base_url": base_url if args.backend == "openai" else None,
        "system_prompt": str(Path(args.system_prompt).resolve()),
        "max_tokens": args.max_tokens if args.max_tokens > 0 else None,
        "response_format": args.response_format,
        "output": str(out_jsonl),
        "resume": args.resume,
        "start_index": args.start_index,
        "status_counts": {"ok": existing_summary["ok"], "error": existing_summary["error"]},
        "entity_count": existing_summary["entity_count"],
        "relation_count": existing_summary["relation_count"],
    }

    mode = "a" if args.resume and out_jsonl.exists() else "w"
    with out_jsonl.open(mode, encoding="utf-8") as wf:
        for idx, chunk in enumerate(rows, start=1):
            try:
                if args.backend == "stub":
                    raw = build_stub_record(chunk)
                else:
                    raw = call_openai_compatible(
                        model,
                        build_messages(system_prompt, chunk),
                        base_url=base_url,
                        api_key=api_key,
                        site_url=args.site_url or None,
                        app_name=args.app_name or None,
                        timeout_seconds=args.request_timeout,
                        max_retries=args.max_retries,
                        retry_sleep_seconds=args.retry_sleep_seconds,
                        max_tokens=args.max_tokens,
                        response_format=args.response_format,
                    )
                    if args.sleep_seconds > 0:
                        time.sleep(args.sleep_seconds)

                entities, relations, warnings = validate_record(raw, schema)
                evidence = {
                    "evidence_id": f"{chunk['chunk_id']}_ev0",
                    "doc_id": chunk.get("doc_id"),
                    "chunk_id": chunk.get("chunk_id"),
                    "title": chunk.get("title"),
                    "year": chunk.get("year"),
                    "source_type": chunk.get("source_type"),
                    "evidence_level": chunk.get("evidence_level"),
                }
                record = {
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_id": chunk.get("doc_id"),
                    "status": "ok",
                    "warnings": warnings,
                    "entities": entities,
                    "relations": relations,
                    "evidence": evidence,
                }
                summary["status_counts"]["ok"] += 1
                summary["entity_count"] += len(entities)
                summary["relation_count"] += len(relations)
            except Exception as exc:
                record = {
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_id": chunk.get("doc_id"),
                    "status": "error",
                    "error": str(exc),
                    "entities": [],
                    "relations": [],
                    "evidence": {
                        "evidence_id": f"{chunk['chunk_id']}_ev0",
                        "doc_id": chunk.get("doc_id"),
                        "chunk_id": chunk.get("chunk_id"),
                        "title": chunk.get("title"),
                        "year": chunk.get("year"),
                        "source_type": chunk.get("source_type"),
                        "evidence_level": chunk.get("evidence_level"),
                    },
                }
                summary["status_counts"]["error"] += 1

            wf.write(json.dumps(record, ensure_ascii=False) + "\n")
            wf.flush()
            if idx % max(1, args.summary_every) == 0 or idx == len(rows):
                print(
                    f"[{idx}/{len(rows)}] ok={summary['status_counts']['ok']} "
                    f"err={summary['status_counts']['error']} "
                    f"entities={summary['entity_count']} relations={summary['relation_count']}"
                )

    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
