#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as wf:
        writer = csv.DictWriter(wf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Export normalized data for Neo4j import")
    ap.add_argument("--entities", default="data/processed/normalized_full/entities.jsonl")
    ap.add_argument("--relations", default="data/processed/normalized_full/relations.jsonl")
    ap.add_argument("--evidence", default="data/processed/normalized_full/evidence.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks_full/chunks.jsonl")
    ap.add_argument("--output", default="data/processed/neo4j_import")
    args = ap.parse_args()

    entities = list(iter_jsonl(Path(args.entities).resolve()))
    relations = list(iter_jsonl(Path(args.relations).resolve()))
    evidence_rows = list(iter_jsonl(Path(args.evidence).resolve()))
    chunks = list(iter_jsonl(Path(args.chunks).resolve()))

    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    entity_nodes = [
        {
            "entity_id:ID(Entity)": row["entity_id"],
            "name": row["name"],
            "canonical_name": row["canonical_name"],
            "type": row["type"],
            "description": row.get("description", ""),
            "synonyms:string[]": "|".join(row.get("synonyms", [])),
            "source_chunk_count:int": row.get("source_chunk_count", 0),
            "source_doc_count:int": row.get("source_doc_count", 0),
            "quality_flags:string[]": "|".join(row.get("quality_flags", [])),
            "is_isolated:boolean": str(bool(row.get("is_isolated", False))).lower(),
            "graph_degree:int": row.get("graph_degree", 0),
            "duplicate_group_key": row.get("duplicate_group_key", ""),
            "duplicate_group_size:int": row.get("duplicate_group_size", 1),
            "merge_candidate_types:string[]": "|".join(row.get("merge_candidate_types", [])),
            "conflict_aliases:string[]": "|".join(row.get("conflict_aliases", [])),
            "tool_category": row.get("tool_category", ""),
            ":LABEL": "Entity",
        }
        for row in entities
    ]
    chunk_nodes = [
        {
            "chunk_id:ID(Chunk)": row["chunk_id"],
            "doc_id": row.get("doc_id"),
            "title": row.get("title"),
            "year:int": row.get("year") if row.get("year") is not None else "",
            "source_type": row.get("source_type"),
            "evidence_level": row.get("evidence_level"),
            "page_start:int": row.get("page_start"),
            "page_end:int": row.get("page_end"),
            "text": row.get("text"),
            ":LABEL": "Chunk",
        }
        for row in chunks
    ]
    evidence_nodes = [
        {
            "evidence_id:ID(Evidence)": row["evidence_id"],
            "doc_id": row.get("doc_id"),
            "chunk_id": row.get("chunk_id"),
            "title": row.get("title"),
            "year:int": row.get("year") if row.get("year") is not None else "",
            "source_type": row.get("source_type"),
            "evidence_level": row.get("evidence_level"),
            ":LABEL": "Evidence",
        }
        for row in evidence_rows
    ]
    entity_relationships = [
        {
            ":START_ID(Entity)": row["src_entity_id"],
            ":END_ID(Entity)": row["dst_entity_id"],
            ":TYPE": row["relation_type"],
            "relation_id": row["relation_id"],
            "confidence:float": row["confidence"],
            "support_count:int": row["support_count"],
            "evidence_text_example": row.get("evidence_text_example", ""),
            "quality_flags:string[]": "|".join(row.get("quality_flags", [])),
            "qa_usage": row.get("qa_usage", ""),
            "evidence_level_summary": row.get("evidence_level_summary", ""),
            "src_type": row.get("src_type", ""),
            "dst_type": row.get("dst_type", ""),
        }
        for row in relations
    ]
    supports_relationships = [
        {
            ":START_ID(Entity)": row["src_entity_id"],
            ":END_ID(Evidence)": evidence_id,
            ":TYPE": "SUPPORTED_BY",
            "relation_id": row["relation_id"],
        }
        for row in relations
        for evidence_id in row.get("support_evidence_ids", [])
    ]
    from_relationships = [
        {
            ":START_ID(Chunk)": row["chunk_id"],
            ":END_ID(Evidence)": row["evidence_id"],
            ":TYPE": "FROM",
        }
        for row in evidence_rows
        if row.get("chunk_id") and row.get("evidence_id")
    ]

    write_csv(out_root / "neo4j_nodes_entity.csv", list(entity_nodes[0].keys()) if entity_nodes else ["entity_id:ID(Entity)", "name", "canonical_name", "type", "description", "synonyms:string[]", "source_chunk_count:int", "source_doc_count:int", "quality_flags:string[]", "is_isolated:boolean", "graph_degree:int", "duplicate_group_key", "duplicate_group_size:int", "merge_candidate_types:string[]", "conflict_aliases:string[]", "tool_category", ":LABEL"], entity_nodes)
    write_csv(out_root / "neo4j_nodes_chunk.csv", list(chunk_nodes[0].keys()) if chunk_nodes else ["chunk_id:ID(Chunk)", "doc_id", "title", "year:int", "source_type", "evidence_level", "page_start:int", "page_end:int", "text", ":LABEL"], chunk_nodes)
    write_csv(out_root / "neo4j_nodes_evidence.csv", list(evidence_nodes[0].keys()) if evidence_nodes else ["evidence_id:ID(Evidence)", "doc_id", "chunk_id", "title", "year:int", "source_type", "evidence_level", ":LABEL"], evidence_nodes)
    write_csv(out_root / "neo4j_relationships_entity.csv", list(entity_relationships[0].keys()) if entity_relationships else [":START_ID(Entity)", ":END_ID(Entity)", ":TYPE", "relation_id", "confidence:float", "support_count:int", "evidence_text_example", "quality_flags:string[]", "qa_usage", "evidence_level_summary", "src_type", "dst_type"], entity_relationships)
    write_csv(out_root / "neo4j_relationships_supports.csv", list(supports_relationships[0].keys()) if supports_relationships else [":START_ID(Entity)", ":END_ID(Evidence)", ":TYPE", "relation_id"], supports_relationships)
    write_csv(out_root / "neo4j_relationships_from.csv", list(from_relationships[0].keys()) if from_relationships else [":START_ID(Chunk)", ":END_ID(Evidence)", ":TYPE"], from_relationships)

    summary = {
        "entities": len(entity_nodes),
        "chunks": len(chunk_nodes),
        "evidence": len(evidence_nodes),
        "entity_relationships": len(entity_relationships),
        "supports_relationships": len(supports_relationships),
        "from_relationships": len(from_relationships),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
