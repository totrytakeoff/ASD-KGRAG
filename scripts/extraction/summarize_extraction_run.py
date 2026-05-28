#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def relation_label(row: dict, relation: dict) -> tuple[str, str, str]:
    entities = {entity.get("entity_id"): entity for entity in row.get("entities", [])}
    src = entities.get(relation.get("src_entity_id"), {})
    dst = entities.get(relation.get("dst_entity_id"), {})
    src_name = src.get("name", "")
    dst_name = dst.get("name", "")
    return src_name, relation.get("relation_type", ""), dst_name


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize an entity/relation extraction JSONL run.")
    ap.add_argument("--input", required=True, help="Extraction JSONL, usually a merged chunk_extractions file")
    ap.add_argument("--output", required=True, help="Output directory for summary files")
    ap.add_argument("--sample-size", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = list(iter_jsonl(input_path))
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    error_rows = [row for row in rows if row.get("status") == "error"]
    entities = [entity for row in ok_rows for entity in row.get("entities", [])]
    relations = [relation for row in ok_rows for relation in row.get("relations", [])]
    warnings = Counter(warning for row in ok_rows for warning in row.get("warnings", []))
    error_messages = Counter(str(row.get("error", ""))[:180] for row in error_rows)

    relation_rows = []
    relation_type_counter = Counter()
    relation_pair_counter = Counter()
    evidence_level_counter = Counter()
    source_type_counter = Counter()

    for row in ok_rows:
        evidence = row.get("evidence") or {}
        evidence_level_counter[evidence.get("evidence_level", "unknown")] += 1
        source_type_counter[evidence.get("source_type", "unknown")] += 1
        for relation in row.get("relations", []):
            src, rel_type, dst = relation_label(row, relation)
            relation_type_counter[rel_type] += 1
            relation_pair_counter[(src, rel_type, dst)] += 1
            relation_rows.append({
                "chunk_id": row.get("chunk_id", ""),
                "doc_id": row.get("doc_id", ""),
                "title": evidence.get("title", ""),
                "year": evidence.get("year", ""),
                "source_type": evidence.get("source_type", ""),
                "evidence_level": evidence.get("evidence_level", ""),
                "src": src,
                "relation_type": rel_type,
                "dst": dst,
                "confidence": relation.get("confidence", ""),
                "evidence_text": relation.get("evidence_text", ""),
            })

    random.seed(args.seed)
    sample_rows = relation_rows[:]
    random.shuffle(sample_rows)
    sample_rows = sample_rows[: args.sample_size]

    summary = {
        "input": str(input_path),
        "rows": len(rows),
        "ok": len(ok_rows),
        "error": len(error_rows),
        "ok_rate": round(len(ok_rows) / len(rows), 4) if rows else None,
        "entities_total": len(entities),
        "relations_total": len(relations),
        "avg_relations_per_ok": round(len(relations) / len(ok_rows), 4) if ok_rows else None,
        "entity_type_distribution": dict(sorted(Counter(entity.get("type", "unknown") for entity in entities).items())),
        "relation_type_distribution": dict(sorted(relation_type_counter.items())),
        "evidence_level_distribution": dict(sorted(evidence_level_counter.items())),
        "source_type_distribution": dict(sorted(source_type_counter.items())),
        "top_warnings": warnings.most_common(30),
        "top_error_messages": error_messages.most_common(20),
        "top_relation_triples": [
            {"src": src, "relation_type": rel_type, "dst": dst, "count": count}
            for (src, rel_type, dst), count in relation_pair_counter.most_common(30)
        ],
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with (output_dir / "relation_samples.csv").open("w", encoding="utf-8", newline="") as wf:
        fieldnames = [
            "chunk_id",
            "doc_id",
            "title",
            "year",
            "source_type",
            "evidence_level",
            "src",
            "relation_type",
            "dst",
            "confidence",
            "evidence_text",
        ]
        writer = csv.DictWriter(wf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sample_rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
