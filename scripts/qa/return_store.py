"""Student return file handling: CSV validation, parsing, and merge logic.

Each return file follows documented CSV templates stored in
``docs/tasks/templates/``.  This module validates headers, parses rows,
and merges accepted data into the project's evaluation or config files.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETURNS_DIR = ROOT / "data" / "student_returns"
EXTRACTED_DIR = RETURNS_DIR / "extracted"

# Task type → expected CSV headers (lowercased, stripped)
EXPECTED_HEADERS: dict[str, list[str]] = {
    "QAQUESTION": [
        "student_id", "question_id", "category", "query",
        "keywords", "requires_guardrail", "source_note", "notes",
    ],
    "SAFETYQUESTION": [
        "student_id", "question_id", "risk_type", "query",
        "keywords", "requires_guardrail", "notes",
    ],
    "ALIAS": [
        "student_id", "entity_name", "entity_type", "chinese_name",
        "english_full_name", "abbreviation", "aliases",
        "version_or_variant", "looks_same_concept", "source_note", "notes",
    ],
    "QAREVIEW": [
        "student_id", "case_id", "query", "off_topic",
        "missing_citation", "over_claim", "missing_guardrail",
        "citation_relevance", "suspicious_sentence", "notes",
    ],
    "CHUNKREVIEW": [
        "student_id", "chunk_id", "title_ok", "year_ok", "readable",
        "asd_related", "severe_truncation", "problem_type", "notes",
    ],
}

# Map task type → merge handler
MERGE_HANDLERS: dict[str, str] = {
    "QAQUESTION": "eval_questions",
    "SAFETYQUESTION": "eval_questions",
    "ALIAS": "alias_candidates",
}


class ValidationError(Exception):
    """Raised when a return file fails validation."""


def detect_task_type(filename: str) -> str | None:
    """Detect task type from filename prefix.

    E.g. ``QAQUESTION_S01_zhangsan_result.csv`` → ``"QAQUESTION"``.
    """
    for task_type in EXPECTED_HEADERS:
        if filename.upper().startswith(task_type):
            return task_type
    return None


def validate_csv(content: str, task_type: str) -> list[dict]:
    """Validate CSV content against expected headers for *task_type*.

    Returns parsed rows (list of dicts).  Raises ``ValidationError``
    on any structural problem.
    """
    expected = EXPECTED_HEADERS.get(task_type)
    if not expected:
        raise ValidationError(f"Unknown task type: {task_type}")

    try:
        reader = csv.DictReader(io.StringIO(content))
    except Exception as exc:
        raise ValidationError(f"Cannot parse CSV: {exc}") from exc

    actual_headers = [h.strip().lower() for h in (reader.fieldnames or [])]

    missing = [h for h in expected if h not in actual_headers]
    if missing:
        raise ValidationError(
            f"Missing required headers for {task_type}: {', '.join(missing)}"
        )

    rows = []
    for line_no, row in enumerate(reader, 2):
        cleaned = {k.strip().lower(): v.strip() for k, v in row.items()}
        # Check required fields (notes is always optional)
        optional = {"notes"}
        for h in expected:
            if h in optional:
                continue
            if not cleaned.get(h):
                raise ValidationError(
                    f"Line {line_no}: missing value for '{h}'"
                )
        rows.append(cleaned)

    if not rows:
        raise ValidationError("CSV is empty (no data rows)")

    return rows


def merge_eval_questions(
    rows: list[dict],
    task_type: str,
    student_id: str,
) -> dict:
    """Merge QAQUESTION / SAFETYQUESTION rows into eval_questions.jsonl.

    Returns a summary of what was added.
    """
    path = ROOT / "scripts" / "qa" / "eval_questions.jsonl"

    from evaluate_qa import read_jsonl, write_jsonl

    existing = read_jsonl(path)
    existing_ids = {q.get("id") for q in existing}

    added = 0
    skipped = 0
    for row in rows:
        qid = row.get("question_id", "")
        if qid in existing_ids:
            skipped += 1
            continue
        existing_ids.add(qid)

        entry = {
            "id": qid,
            "category": row.get("category", "general"),
            "query": row.get("query", ""),
            "keywords": [
                kw.strip() for kw in row.get("keywords", "").split(";") if kw.strip()
            ],
            "requires_guardrail": row.get("requires_guardrail", "").lower() == "true",
            "source_note": row.get("source_note", ""),
            "student_id": student_id,
            "task_type": task_type,
            "merged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        if task_type == "SAFETYQUESTION":
            entry["risk_type"] = row.get("risk_type", "general")

        existing.append(entry)
        added += 1

    write_jsonl(path, existing)

    # Tag questions for safety
    for row in rows:
        qid = row.get("question_id", "")
        if row.get("requires_guardrail", "").lower() == "true":
            for q in existing:
                if q.get("id") == qid and q.get("requires_guardrail") is False:
                    q["requires_guardrail"] = True
                    break

    return {"added": added, "skipped": skipped, "total": len(existing)}


def merge_alias_candidates(rows: list[dict], student_id: str) -> dict:
    """Merge ALIAS rows into curated_entity_alias_map.json candidate area.

    We append a temporary ``_candidates`` key so a human can review before
    actually merging groups.
    """
    path = ROOT / "config" / "graph" / "curated_entity_alias_map.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"description": "", "groups": [], "_candidates": []}

    candidates = data.setdefault("_candidates", [])
    before = len(candidates)

    for row in rows:
        aliases_raw = row.get("aliases", "")
        alias_list = [a.strip() for a in aliases_raw.split(";") if a.strip()]
        # Always include the entity name itself
        if row.get("entity_name") and row["entity_name"] not in alias_list:
            alias_list.insert(0, row["entity_name"])

        candidate = {
            "entity_name": row.get("entity_name", ""),
            "entity_type": row.get("entity_type", ""),
            "chinese_name": row.get("chinese_name", ""),
            "english_full_name": row.get("english_full_name", ""),
            "abbreviation": row.get("abbreviation", ""),
            "aliases": alias_list,
            "version_or_variant": row.get("version_or_variant", ""),
            "looks_same_concept": row.get("looks_same_concept", "uncertain"),
            "source_note": row.get("source_note", ""),
            "student_id": student_id,
            "merged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        # Avoid exact duplicates
        if not any(
            c["entity_name"] == candidate["entity_name"]
            and c["student_id"] == candidate["student_id"]
            for c in candidates
        ):
            candidates.append(candidate)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"added": len(candidates) - before, "total_candidates": len(candidates)}


def store_return_file(
    filename: str,
    content: str | bytes,
) -> dict:
    """Validate and store a student return file.

    Steps:
    1. Detect task type from filename.
    2. Decode content to text (if bytes).
    3. Validate CSV headers and row structure.
    4. Save raw file to ``data/student_returns/raw/``.
    5. Run merge handler.

    Returns dict with keys: ``task_type``, ``valid``, ``rows``, ``merge_result``.
    """
    task_type = detect_task_type(filename)
    if not task_type:
        raise ValidationError(
            f"Cannot detect task type from filename: {filename}. "
            f"Filename must start with one of: {', '.join(EXPECTED_HEADERS)}"
        )

    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")

    rows = validate_csv(content, task_type)

    # Save raw file
    raw_dir = RETURNS_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / filename).write_text(content, encoding="utf-8")

    # Merge
    student_id = rows[0].get("student_id", "unknown") if rows else "unknown"
    handler = MERGE_HANDLERS.get(task_type)
    merge_result = None
    if handler == "eval_questions":
        merge_result = merge_eval_questions(rows, task_type, student_id)
    elif handler == "alias_candidates":
        merge_result = merge_alias_candidates(rows, student_id)

    return {
        "task_type": task_type,
        "valid": True,
        "rows_count": len(rows),
        "student_id": student_id,
        "filename": filename,
        "merge_result": merge_result,
    }


def list_returns() -> list[dict]:
    """List all stored return files with metadata."""
    raw_dir = RETURNS_DIR / "raw"
    if not raw_dir.exists():
        return []
    entries = []
    for p in sorted(raw_dir.iterdir(), reverse=True):
        if p.is_file():
            task_type = detect_task_type(p.name) or "UNKNOWN"
            entries.append({
                "filename": p.name,
                "task_type": task_type,
                "size": p.stat().st_size,
                "modified": p.stat().st_mtime,
            })
    return entries


def delete_return(filename: str) -> bool:
    """Delete a stored return file. Returns True if deleted."""
    raw_dir = RETURNS_DIR / "raw"
    target = raw_dir / filename
    if target.exists() and target.is_file():
        target.unlink()
        return True
    return False


def read_alias_map() -> dict:
    """Read the curated entity alias map."""
    path = ROOT / "config" / "graph" / "curated_entity_alias_map.json"
    if not path.exists():
        return {"description": "", "groups": [], "_candidates": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"description": "", "groups": [], "_candidates": []}


def write_alias_map(data: dict) -> dict:
    """Write the curated entity alias map. Returns the saved data."""
    path = ROOT / "config" / "graph" / "curated_entity_alias_map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
