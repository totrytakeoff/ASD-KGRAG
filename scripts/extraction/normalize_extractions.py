#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
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


def normalize_name(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff\s()/\-]", "", text)
    return text.strip()


def make_entity_id(entity_type: str, canonical_name: str) -> str:
    digest = hashlib.sha1(f"{entity_type}|{canonical_name}".encode("utf-8")).hexdigest()[:12]
    return f"ent_{digest}"


def make_relation_id(src_entity_id: str, relation_type: str, dst_entity_id: str) -> str:
    digest = hashlib.sha1(f"{src_entity_id}|{relation_type}|{dst_entity_id}".encode("utf-8")).hexdigest()[:12]
    return f"rel_{digest}"


def pick_best_name(counter: Counter) -> str:
    if not counter:
        return ""
    return sorted(counter.items(), key=lambda item: (-item[1], len(item[0]), item[0]))[0][0]


def get_or_create_entity_group(
    entity_groups: list[dict],
    entity_type: str,
    aliases: set[str],
) -> dict:
    for group in entity_groups:
        if group["entity_type"] != entity_type:
            continue
        if group["normalized_aliases"] & aliases:
            group["normalized_aliases"].update(aliases)
            return group

    group = {
        "entity_type": entity_type,
        "canonical_name": min(aliases) if aliases else "",
        "normalized_aliases": set(aliases),
        "name_counter": Counter(),
        "description_counter": Counter(),
        "synonyms": set(),
        "source_chunk_ids": set(),
        "source_doc_ids": set(),
    }
    entity_groups.append(group)
    return group


def normalize_extractions(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    entity_groups: list[dict] = []
    relation_groups: dict[tuple[int, str, int], dict] = {}
    evidence_rows: list[dict] = []

    for row in rows:
        if row.get("status") != "ok":
            continue

        evidence = row.get("evidence", {})
        evidence_rows.append(evidence)

        local_entity_map: dict[str, str] = {}
        for entity in row.get("entities", []):
            entity_type = entity.get("type", "")
            aliases = {normalize_name(entity.get("name", ""))}
            for synonym in entity.get("synonyms", []) or []:
                aliases.add(normalize_name(synonym))
            aliases = {alias for alias in aliases if alias}
            if not entity_type or not aliases:
                continue

            group = get_or_create_entity_group(entity_groups, entity_type, aliases)
            group["canonical_name"] = min(group["normalized_aliases"]) if group["normalized_aliases"] else group["canonical_name"]
            display_name = entity.get("name", "").strip() or group["canonical_name"]
            group["name_counter"][display_name] += 1
            description = (entity.get("description") or "").strip()
            if description:
                group["description_counter"][description] += 1
            group["synonyms"].add(display_name)
            for synonym in entity.get("synonyms", []) or []:
                synonym = (synonym or "").strip()
                if synonym:
                    group["synonyms"].add(synonym)
            if row.get("chunk_id"):
                group["source_chunk_ids"].add(row["chunk_id"])
            if row.get("doc_id"):
                group["source_doc_ids"].add(row["doc_id"])

            local_entity_map[entity.get("entity_id")] = entity_groups.index(group)

        for relation in row.get("relations", []):
            src_group_idx = local_entity_map.get(relation.get("src_entity_id"))
            dst_group_idx = local_entity_map.get(relation.get("dst_entity_id"))
            relation_type = relation.get("relation_type")
            if src_group_idx is None or dst_group_idx is None or not relation_type:
                continue

            key = (src_group_idx, relation_type, dst_group_idx)
            if key not in relation_groups:
                relation_groups[key] = {
                    "src_group_idx": src_group_idx,
                    "relation_type": relation_type,
                    "dst_group_idx": dst_group_idx,
                    "confidence_values": [],
                    "evidence_texts": [],
                    "support_chunk_ids": set(),
                    "support_doc_ids": set(),
                    "support_evidence_ids": set(),
                }

            group = relation_groups[key]
            try:
                group["confidence_values"].append(float(relation.get("confidence", 0)))
            except (TypeError, ValueError):
                group["confidence_values"].append(0.0)
            evidence_text = (relation.get("evidence_text") or "").strip()
            if evidence_text:
                group["evidence_texts"].append(evidence_text)
            if row.get("chunk_id"):
                group["support_chunk_ids"].add(row["chunk_id"])
            if row.get("doc_id"):
                group["support_doc_ids"].add(row["doc_id"])
            if evidence.get("evidence_id"):
                group["support_evidence_ids"].add(evidence["evidence_id"])

    entities_out: list[dict] = []
    canonical_map: dict[str, list[str]] = {}
    group_idx_to_entity_id: dict[int, str] = {}
    sorted_groups = sorted(enumerate(entity_groups), key=lambda item: (item[1]["entity_type"], item[1]["canonical_name"]))
    for original_idx, group in sorted_groups:
        entity_type = group["entity_type"]
        canonical_name = group["canonical_name"]
        entity_id = make_entity_id(entity_type, canonical_name)
        group_idx_to_entity_id[original_idx] = entity_id
        name = pick_best_name(group["name_counter"])
        description = pick_best_name(group["description_counter"])
        synonyms = sorted(s for s in group["synonyms"] if s and normalize_name(s) != canonical_name)
        entities_out.append(
            {
                "entity_id": entity_id,
                "name": name,
                "canonical_name": canonical_name,
                "type": entity_type,
                "description": description,
                "synonyms": synonyms,
                "source_chunk_count": len(group["source_chunk_ids"]),
                "source_doc_count": len(group["source_doc_ids"]),
                "source_chunk_ids": sorted(group["source_chunk_ids"]),
                "source_doc_ids": sorted(group["source_doc_ids"]),
            }
        )
        canonical_map[name] = synonyms

    relations_out: list[dict] = []
    for key, group in sorted(relation_groups.items()):
        src_entity_id = group_idx_to_entity_id[group["src_group_idx"]]
        dst_entity_id = group_idx_to_entity_id[group["dst_group_idx"]]
        relation_id = make_relation_id(src_entity_id, group["relation_type"], dst_entity_id)
        avg_confidence = round(sum(group["confidence_values"]) / max(1, len(group["confidence_values"])), 4)
        relations_out.append(
            {
                "relation_id": relation_id,
                "src_entity_id": src_entity_id,
                "relation_type": group["relation_type"],
                "dst_entity_id": dst_entity_id,
                "confidence": avg_confidence,
                "support_count": len(group["support_evidence_ids"]),
                "evidence_text_example": group["evidence_texts"][0] if group["evidence_texts"] else "",
                "support_chunk_ids": sorted(group["support_chunk_ids"]),
                "support_doc_ids": sorted(group["support_doc_ids"]),
                "support_evidence_ids": sorted(group["support_evidence_ids"]),
            }
        )

    return entities_out, relations_out, evidence_rows, canonical_map


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize extracted entities and relations")
    ap.add_argument("--input", default="data/processed/extraction_full/chunk_extractions.jsonl")
    ap.add_argument("--output", default="data/processed/normalized_full")
    args = ap.parse_args()

    rows = list(iter_jsonl(Path(args.input).resolve()))
    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    entities, relations, evidence_rows, canonical_map = normalize_extractions(rows)
    write_jsonl(out_root / "entities.jsonl", entities)
    write_jsonl(out_root / "relations.jsonl", relations)
    write_jsonl(out_root / "evidence.jsonl", evidence_rows)
    (out_root / "entity_canonical_map.json").write_text(json.dumps(canonical_map, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "input_rows": len(rows),
        "entities_total": len(entities),
        "relations_total": len(relations),
        "evidence_total": len(evidence_rows),
        "entity_type_distribution": dict(Counter(row["type"] for row in entities)),
        "relation_type_distribution": dict(Counter(row["relation_type"] for row in relations)),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
