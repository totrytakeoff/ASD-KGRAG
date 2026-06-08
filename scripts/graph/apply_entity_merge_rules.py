#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def pick_primary(entities: list[dict]) -> dict:
    return sorted(
        entities,
        key=lambda row: (
            -int(row.get("source_chunk_count") or 0),
            -int(row.get("source_doc_count") or 0),
            len(row.get("canonical_name") or ""),
            row.get("entity_id") or "",
        ),
    )[0]


def normalize_alias(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def entity_aliases(entity: dict) -> set[str]:
    values = {entity.get("name", ""), entity.get("canonical_name", "")}
    values.update(entity.get("synonyms", []) or [])
    return {normalize_alias(value) for value in values if normalize_alias(value)}


def merge_entities(group: list[dict], primary: dict) -> dict:
    merged = dict(primary)
    synonyms = set(primary.get("synonyms", []) or [])
    flags = set(primary.get("quality_flags", []) or [])
    source_chunk_ids = set(primary.get("source_chunk_ids", []) or [])
    source_doc_ids = set(primary.get("source_doc_ids", []) or [])
    descriptions = Counter()
    names = Counter()

    for entity in group:
        names[entity.get("name") or ""] += int(entity.get("source_chunk_count") or 1)
        if entity.get("description"):
            descriptions[entity["description"]] += int(entity.get("source_chunk_count") or 1)
        for value in [entity.get("name"), entity.get("canonical_name")]:
            if value and value != primary.get("canonical_name"):
                synonyms.add(value)
        synonyms.update(entity.get("synonyms", []) or [])
        flags.update(entity.get("quality_flags", []) or [])
        source_chunk_ids.update(entity.get("source_chunk_ids", []) or [])
        source_doc_ids.update(entity.get("source_doc_ids", []) or [])

    flags.add("merged_same_type_same_name")
    merged["name"] = names.most_common(1)[0][0] if names else primary.get("name", "")
    merged["description"] = descriptions.most_common(1)[0][0] if descriptions else primary.get("description", "")
    merged["synonyms"] = sorted(s for s in synonyms if s and s != merged.get("canonical_name"))
    merged["quality_flags"] = sorted(flags)
    merged["source_chunk_ids"] = sorted(source_chunk_ids)
    merged["source_doc_ids"] = sorted(source_doc_ids)
    merged["source_chunk_count"] = len(source_chunk_ids)
    merged["source_doc_count"] = len(source_doc_ids)
    return merged


def load_alias_groups(path: Path | None) -> dict[tuple[str, str], str]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    alias_to_group: dict[tuple[str, str], str] = {}
    for group in data.get("groups", []):
        entity_type = group["type"]
        group_id = group["group_id"]
        aliases = {group_id}
        aliases.update(group.get("aliases", []) or [])
        for alias in aliases:
            key = (entity_type, normalize_alias(alias))
            if key in alias_to_group and alias_to_group[key] != group_id:
                raise ValueError(f"Alias maps to multiple groups: {entity_type} {alias}")
            alias_to_group[key] = group_id
    return alias_to_group


def merge_relations(relations: list[dict], entity_id_map: dict[str, str]) -> list[dict]:
    groups: dict[tuple[str, str, str], dict] = {}
    for relation in relations:
        src = entity_id_map.get(relation.get("src_entity_id"), relation.get("src_entity_id"))
        dst = entity_id_map.get(relation.get("dst_entity_id"), relation.get("dst_entity_id"))
        if not src or not dst:
            continue
        relation_type = relation.get("relation_type")
        if not relation_type:
            continue
        if src == dst:
            continue
        key = (src, relation_type, dst)
        if key not in groups:
            row = dict(relation)
            row["src_entity_id"] = src
            row["dst_entity_id"] = dst
            row["confidence_values"] = []
            row["support_chunk_ids"] = []
            row["support_doc_ids"] = []
            row["support_evidence_ids"] = []
            row["evidence_texts"] = []
            row["quality_flags"] = set(row.get("quality_flags", []) or [])
            groups[key] = row
        target = groups[key]
        try:
            target["confidence_values"].append(float(relation.get("confidence") or 0))
        except (TypeError, ValueError):
            target["confidence_values"].append(0.0)
        target["support_chunk_ids"].extend(relation.get("support_chunk_ids", []) or [])
        target["support_doc_ids"].extend(relation.get("support_doc_ids", []) or [])
        target["support_evidence_ids"].extend(relation.get("support_evidence_ids", []) or [])
        if relation.get("evidence_text_example"):
            target["evidence_texts"].append(relation["evidence_text_example"])
        target["quality_flags"].update(relation.get("quality_flags", []) or [])

    out: list[dict] = []
    for (src, relation_type, dst), row in sorted(groups.items()):
        confidence_values = row.pop("confidence_values")
        evidence_texts = row.pop("evidence_texts")
        row["confidence"] = round(sum(confidence_values) / max(1, len(confidence_values)), 4)
        row["support_chunk_ids"] = sorted(set(row["support_chunk_ids"]))
        row["support_doc_ids"] = sorted(set(row["support_doc_ids"]))
        row["support_evidence_ids"] = sorted(set(row["support_evidence_ids"]))
        row["support_count"] = len(row["support_evidence_ids"])
        row["evidence_text_example"] = evidence_texts[0] if evidence_texts else row.get("evidence_text_example", "")
        row["quality_flags"] = sorted(row["quality_flags"])
        row["relation_id"] = row.get("relation_id") or f"rel_{len(out):08d}"
        # Keep existing IDs when possible; duplicate remaps are still safe because relation_id
        # is only used as an attribute, not as an import identity.
        out.append(row)
    return out


DEFAULT_MERGE_TYPES = {
    "AssessmentTool",
    "Intervention",
    "Condition",
    "Symptom",
    "Comorbidity",
    "Risk",
}


def group_key_for_entity(entity: dict, merge_types: set[str], alias_to_group: dict[tuple[str, str], str]) -> tuple[str, str]:
    entity_type = entity.get("type", "")
    if entity_type in merge_types:
        for alias in sorted(entity_aliases(entity)):
            curated_group = alias_to_group.get((entity_type, alias))
            if curated_group:
                return entity_type, f"curated:{curated_group}"
    return (
        entity_type,
        entity.get("duplicate_group_key") or entity.get("canonical_name") or entity.get("name") or "",
    )


def merge_reason(key: tuple[str, str]) -> str:
    return "curated_alias_map" if key[1].startswith("curated:") else "same_type_same_name"


def apply_same_type_same_name_merge(
    input_dir: Path,
    output_dir: Path,
    merge_types: set[str],
    alias_to_group: dict[tuple[str, str], str] | None = None,
) -> dict:
    entities = list(iter_jsonl(input_dir / "entities.jsonl"))
    relations = list(iter_jsonl(input_dir / "relations.jsonl"))
    evidence = list(iter_jsonl(input_dir / "evidence.jsonl"))
    alias_to_group = alias_to_group or {}

    output_dir.mkdir(parents=True, exist_ok=True)

    by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entity in entities:
        key = group_key_for_entity(entity, merge_types, alias_to_group)
        by_group[key].append(entity)

    entity_id_map: dict[str, str] = {}
    merged_entities: list[dict] = []
    merge_groups: list[dict] = []
    for key, group in sorted(by_group.items()):
        if len(group) == 1 or key[0] not in merge_types:
            entity = group[0]
            entity_id_map[entity["entity_id"]] = entity["entity_id"]
            merged_entities.extend(group if len(group) > 1 else [entity])
            continue
        primary = pick_primary(group)
        for entity in group:
            entity_id_map[entity["entity_id"]] = primary["entity_id"]
        merged = merge_entities(group, primary)
        reason = merge_reason(key)
        flags = set(merged.get("quality_flags", []) or [])
        flags.add(f"merged_by:{reason}")
        merged["quality_flags"] = sorted(flags)
        merged_entities.append(merged)
        merge_groups.append(
            {
                "type": key[0],
                "duplicate_group_key": key[1],
                "reason": reason,
                "primary_entity_id": primary["entity_id"],
                "merged_entity_ids": [entity["entity_id"] for entity in group if entity["entity_id"] != primary["entity_id"]],
                "entity_count": len(group),
                "source_chunk_count_total": sum(int(entity.get("source_chunk_count") or 0) for entity in group),
                "names": sorted({entity.get("name", "") for entity in group if entity.get("name")}),
                "canonical_names": sorted({entity.get("canonical_name", "") for entity in group if entity.get("canonical_name")}),
            }
        )

    merged_relations = merge_relations(relations, entity_id_map)

    write_jsonl(output_dir / "entities.jsonl", sorted(merged_entities, key=lambda row: (row.get("type", ""), row.get("canonical_name", ""))))
    write_jsonl(output_dir / "relations.jsonl", merged_relations)
    write_jsonl(output_dir / "evidence.jsonl", evidence)

    summary = {
        "input_entities": len(entities),
        "output_entities": len(merged_entities),
        "merged_entity_delta": len(entities) - len(merged_entities),
        "merge_groups": len(merge_groups),
        "input_relations": len(relations),
        "output_relations": len(merged_relations),
        "relation_delta": len(relations) - len(merged_relations),
        "merge_reasons": dict(Counter(group["reason"] for group in merge_groups)),
    }
    (output_dir / "merge_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "merge_groups.json").write_text(json.dumps(merge_groups, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply conservative entity merge rules to normalized graph data.")
    ap.add_argument("--input-dir", default="data/processed/normalized_full_ab_nonbook_v5_current_quality")
    ap.add_argument("--output-dir", default="data/processed/normalized_full_ab_nonbook_v5_current_curated_base")
    ap.add_argument(
        "--merge-types",
        nargs="+",
        default=sorted(DEFAULT_MERGE_TYPES),
        help="Entity types eligible for same-type same-name merging.",
    )
    ap.add_argument(
        "--alias-map",
        default="",
        help="Optional curated alias map JSON. Only same-type entities are merged.",
    )
    args = ap.parse_args()
    alias_to_group = load_alias_groups(Path(args.alias_map).resolve()) if args.alias_map else {}
    apply_same_type_same_name_merge(
        Path(args.input_dir).resolve(),
        Path(args.output_dir).resolve(),
        set(args.merge_types),
        alias_to_group,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
