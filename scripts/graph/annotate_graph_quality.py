#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def normalize_key(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff\s()/\-]", "", text)
    return text.strip()


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = normalize_key(text)
    return any(marker.lower() in lowered for marker in markers)


CLINICAL_TOOL_MARKERS = (
    "ados",
    "adi-r",
    "adi",
    "m-chat",
    "chat",
    "cars",
    "abc",
    "atec",
    "srs",
    "scq",
    "aq",
    "cast",
    "stat",
    "dsm",
    "量表",
    "问卷",
    "访谈",
    "观察表",
    "评定量表",
    "筛查表",
    "诊断标准",
)

RESEARCH_MODALITY_MARKERS = (
    "eeg",
    "erp",
    "fmri",
    "smri",
    "mri",
    "fnirs",
    "meg",
    "pet",
    "eye-tracking",
    "眼动",
    "脑电",
    "磁共振",
    "近红外",
    "功能连接",
)

DIGITAL_ALGORITHM_MARKERS = (
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "computer vision",
    "neural network",
    "random forest",
    "support vector",
    "svm",
    "人工智能",
    "机器学习",
    "深度学习",
    "计算机视觉",
    "算法",
    "分类器",
)

DERIVED_ENTITY_FLAG_PREFIXES = (
    "assessment_tool_category:",
)

DERIVED_ENTITY_FLAGS = {
    "isolated_entity",
    "alias_type_conflict",
    "same_name_duplicate",
    "single_chunk_entity",
}

DERIVED_RELATION_FLAG_PREFIXES = (
    "measurement_tool_category:",
)

DERIVED_RELATION_FLAGS = {
    "single_evidence_relation",
    "low_confidence",
    "clinical_answer_requires_evidence_guardrail",
    "self_relation",
}

GENERIC_TOOL_MARKERS = (
    "technology",
    "technique",
    "method",
    "approach",
    "工具",
    "技术",
    "方法",
)


def classify_tool(entity: dict) -> str:
    haystack = " ".join(
        [
            entity.get("name", ""),
            entity.get("canonical_name", ""),
            " ".join(entity.get("synonyms", []) or []),
            entity.get("description", ""),
        ]
    )
    if contains_any(haystack, DIGITAL_ALGORITHM_MARKERS):
        return "digital_algorithm"
    if contains_any(haystack, CLINICAL_TOOL_MARKERS):
        return "clinical_assessment"
    if contains_any(haystack, RESEARCH_MODALITY_MARKERS):
        return "research_modality"
    if contains_any(haystack, GENERIC_TOOL_MARKERS):
        return "generic_method"
    return "unspecified_assessment"


def preserved_flags(flags: list[str], derived_flags: set[str], derived_prefixes: tuple[str, ...]) -> list[str]:
    out = []
    for flag in flags:
        if flag in derived_flags:
            continue
        if any(flag.startswith(prefix) for prefix in derived_prefixes):
            continue
        out.append(flag)
    return out


def evidence_level_summary(relation: dict, evidence_by_id: dict[str, dict]) -> str:
    counter = Counter()
    for evidence_id in relation.get("support_evidence_ids", []) or []:
        level = (evidence_by_id.get(evidence_id) or {}).get("evidence_level") or "unknown"
        counter[level] += 1
    return "|".join(f"{key}:{value}" for key, value in sorted(counter.items())) if counter else ""


def annotate(input_dir: Path, output_dir: Path) -> dict:
    entities = list(iter_jsonl(input_dir / "entities.jsonl"))
    relations = list(iter_jsonl(input_dir / "relations.jsonl"))
    evidence_rows = list(iter_jsonl(input_dir / "evidence.jsonl"))

    output_dir.mkdir(parents=True, exist_ok=True)

    entity_by_id = {row["entity_id"]: row for row in entities}
    evidence_by_id = {row["evidence_id"]: row for row in evidence_rows}

    connected_entity_ids = set()
    relation_counts_by_entity: Counter[str] = Counter()
    for relation in relations:
        src = relation.get("src_entity_id")
        dst = relation.get("dst_entity_id")
        if src:
            connected_entity_ids.add(src)
            relation_counts_by_entity[src] += 1
        if dst:
            connected_entity_ids.add(dst)
            relation_counts_by_entity[dst] += 1

    name_groups: dict[str, list[dict]] = defaultdict(list)
    alias_groups: dict[str, list[dict]] = defaultdict(list)
    for entity in entities:
        names = {entity.get("name", ""), entity.get("canonical_name", "")}
        names.update(entity.get("synonyms", []) or [])
        for name in names:
            key = normalize_key(name)
            if key:
                alias_groups[key].append(entity)
        name_key = normalize_key(entity.get("name") or entity.get("canonical_name"))
        if name_key:
            name_groups[name_key].append(entity)

    conflict_keys = {
        key
        for key, group in alias_groups.items()
        if len({entity.get("type") for entity in group}) > 1
    }

    canonical_tool_category: dict[str, str] = {}
    for entity in entities:
        if entity.get("type") == "AssessmentTool":
            canonical_tool_category[entity["entity_id"]] = classify_tool(entity)

    enriched_entities: list[dict] = []
    for entity in entities:
        row = dict(entity)
        flags: list[str] = preserved_flags(
            entity.get("quality_flags", []) or [],
            DERIVED_ENTITY_FLAGS,
            DERIVED_ENTITY_FLAG_PREFIXES,
        )
        aliases = {normalize_key(entity.get("name", "")), normalize_key(entity.get("canonical_name", ""))}
        aliases.update(normalize_key(synonym) for synonym in entity.get("synonyms", []) or [])
        aliases = {alias for alias in aliases if alias}
        conflict_aliases = sorted(alias for alias in aliases if alias in conflict_keys)
        duplicate_group_key = normalize_key(entity.get("name") or entity.get("canonical_name"))
        duplicate_group = name_groups.get(duplicate_group_key, [])
        duplicate_types = sorted({item.get("type", "") for item in duplicate_group if item.get("type")})

        is_isolated = entity["entity_id"] not in connected_entity_ids
        if is_isolated:
            flags.append("isolated_entity")
        if conflict_aliases:
            flags.append("alias_type_conflict")
        if len(duplicate_group) > 1:
            flags.append("same_name_duplicate")
        if entity.get("source_chunk_count", 0) <= 1:
            flags.append("single_chunk_entity")

        tool_category = ""
        if entity.get("type") == "AssessmentTool":
            tool_category = canonical_tool_category.get(entity["entity_id"], "unspecified_assessment")
            if tool_category in {"research_modality", "digital_algorithm", "generic_method"}:
                flags.append(f"assessment_tool_category:{tool_category}")

        row.update(
            {
                "quality_flags": sorted(set(flags)),
                "is_isolated": is_isolated,
                "graph_degree": relation_counts_by_entity[entity["entity_id"]],
                "duplicate_group_key": duplicate_group_key,
                "duplicate_group_size": len(duplicate_group),
                "merge_candidate_types": duplicate_types,
                "conflict_aliases": conflict_aliases,
                "tool_category": tool_category,
            }
        )
        enriched_entities.append(row)

    enriched_relations: list[dict] = []
    for relation in relations:
        row = dict(relation)
        flags: list[str] = preserved_flags(
            relation.get("quality_flags", []) or [],
            DERIVED_RELATION_FLAGS,
            DERIVED_RELATION_FLAG_PREFIXES,
        )
        src = entity_by_id.get(relation.get("src_entity_id"), {})
        dst = entity_by_id.get(relation.get("dst_entity_id"), {})
        support_count = int(relation.get("support_count") or 0)
        confidence = float(relation.get("confidence") or 0)

        if support_count <= 1:
            flags.append("single_evidence_relation")
        if confidence < 0.5:
            flags.append("low_confidence")
        if relation.get("relation_type") == "MEASURED_BY" and dst.get("type") == "AssessmentTool":
            tool_category = canonical_tool_category.get(dst.get("entity_id", ""), "")
            if tool_category in {"research_modality", "digital_algorithm", "generic_method"}:
                flags.append(f"measurement_tool_category:{tool_category}")
        if relation.get("relation_type") in {"INDICATED_FOR", "NOT_INDICATED_FOR", "HAS_RISK"}:
            flags.append("clinical_answer_requires_evidence_guardrail")
        if src.get("entity_id") == dst.get("entity_id"):
            flags.append("self_relation")

        qa_usage = "standard"
        if "low_confidence" in flags or "single_evidence_relation" in flags:
            qa_usage = "use_with_caution"
        if any(flag.startswith("measurement_tool_category:") for flag in flags):
            qa_usage = "research_context_only"
        if "clinical_answer_requires_evidence_guardrail" in flags:
            qa_usage = "guardrailed_clinical_context"

        row.update(
            {
                "quality_flags": sorted(set(flags)),
                "qa_usage": qa_usage,
                "evidence_level_summary": evidence_level_summary(relation, evidence_by_id),
                "src_type": src.get("type", ""),
                "dst_type": dst.get("type", ""),
            }
        )
        enriched_relations.append(row)

    write_jsonl(output_dir / "entities.jsonl", enriched_entities)
    write_jsonl(output_dir / "relations.jsonl", enriched_relations)
    write_jsonl(output_dir / "evidence.jsonl", evidence_rows)

    duplicate_groups = []
    for key, group in sorted(name_groups.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(group) <= 1:
            continue
        duplicate_groups.append(
            {
                "name_key": key,
                "count": len(group),
                "types": sorted({entity.get("type", "") for entity in group}),
                "entities": [
                    {
                        "entity_id": entity["entity_id"],
                        "name": entity.get("name", ""),
                        "canonical_name": entity.get("canonical_name", ""),
                        "type": entity.get("type", ""),
                        "source_chunk_count": entity.get("source_chunk_count", 0),
                    }
                    for entity in group
                ],
            }
        )

    relation_flag_counts = Counter(flag for row in enriched_relations for flag in row["quality_flags"])
    entity_flag_counts = Counter(flag for row in enriched_entities for flag in row["quality_flags"])
    tool_category_counts = Counter(row.get("tool_category") for row in enriched_entities if row.get("tool_category"))
    qa_usage_counts = Counter(row.get("qa_usage") for row in enriched_relations)

    summary = {
        "entities_total": len(enriched_entities),
        "relations_total": len(enriched_relations),
        "evidence_total": len(evidence_rows),
        "isolated_entities": sum(1 for row in enriched_entities if row["is_isolated"]),
        "same_name_duplicate_groups": len(duplicate_groups),
        "alias_type_conflict_entities": sum(1 for row in enriched_entities if "alias_type_conflict" in row["quality_flags"]),
        "entity_quality_flag_distribution": dict(entity_flag_counts),
        "relation_quality_flag_distribution": dict(relation_flag_counts),
        "tool_category_distribution": dict(tool_category_counts),
        "qa_usage_distribution": dict(qa_usage_counts),
    }
    (output_dir / "quality_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "duplicate_entity_groups.json").write_text(
        json.dumps(duplicate_groups[:500], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Annotate normalized graph data with quality metadata.")
    ap.add_argument("--input-dir", default="data/processed/normalized_full_ab_nonbook_v5_current_revalidated")
    ap.add_argument("--output-dir", default="data/processed/normalized_full_ab_nonbook_v5_current_quality")
    args = ap.parse_args()
    annotate(Path(args.input_dir).resolve(), Path(args.output_dir).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
