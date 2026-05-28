#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


TEMPLATE = """// Generated Cypher loader for ASD-KGRAG current Neo4j CSV exports.
// Copy the CSV files into Neo4j's import directory, then run this file with cypher-shell.
//
// Example:
//   cp {csv_dir}/*.csv $NEO4J_HOME/import/asd_kgrag/
//   cypher-shell -u neo4j -p '<password>' -f {output_name}

CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT chunk_id IF NOT EXISTS
FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE;

CREATE CONSTRAINT evidence_id IF NOT EXISTS
FOR (n:Evidence) REQUIRE n.evidence_id IS UNIQUE;

CREATE INDEX entity_type IF NOT EXISTS
FOR (n:Entity) ON (n.type);

CREATE INDEX entity_name IF NOT EXISTS
FOR (n:Entity) ON (n.name);

CREATE INDEX chunk_doc_id IF NOT EXISTS
FOR (n:Chunk) ON (n.doc_id);

CREATE INDEX evidence_level IF NOT EXISTS
FOR (n:Evidence) ON (n.evidence_level);

// Optional reset for iterative local loading.
// MATCH (n) DETACH DELETE n;

LOAD CSV WITH HEADERS FROM 'file:///{import_subdir}/neo4j_nodes_entity.csv' AS row
MERGE (n:Entity {{entity_id: row.`entity_id:ID(Entity)`}})
SET n.name = row.name,
    n.canonical_name = row.canonical_name,
    n.type = row.type,
    n.description = row.description,
    n.synonyms = CASE
      WHEN row.`synonyms:string[]` IS NULL OR row.`synonyms:string[]` = '' THEN []
      ELSE split(row.`synonyms:string[]`, '|')
    END,
    n.source_chunk_count = toInteger(row.`source_chunk_count:int`),
    n.source_doc_count = toInteger(row.`source_doc_count:int`);

LOAD CSV WITH HEADERS FROM 'file:///{import_subdir}/neo4j_nodes_chunk.csv' AS row
MERGE (n:Chunk {{chunk_id: row.`chunk_id:ID(Chunk)`}})
SET n.doc_id = row.doc_id,
    n.title = row.title,
    n.year = CASE WHEN row.`year:int` = '' THEN NULL ELSE toInteger(row.`year:int`) END,
    n.source_type = row.source_type,
    n.evidence_level = row.evidence_level,
    n.page_start = CASE WHEN row.`page_start:int` = '' THEN NULL ELSE toInteger(row.`page_start:int`) END,
    n.page_end = CASE WHEN row.`page_end:int` = '' THEN NULL ELSE toInteger(row.`page_end:int`) END,
    n.text = row.text;

LOAD CSV WITH HEADERS FROM 'file:///{import_subdir}/neo4j_nodes_evidence.csv' AS row
MERGE (n:Evidence {{evidence_id: row.`evidence_id:ID(Evidence)`}})
SET n.doc_id = row.doc_id,
    n.chunk_id = row.chunk_id,
    n.title = row.title,
    n.year = CASE WHEN row.`year:int` = '' THEN NULL ELSE toInteger(row.`year:int`) END,
    n.source_type = row.source_type,
    n.evidence_level = row.evidence_level;

LOAD CSV WITH HEADERS FROM 'file:///{import_subdir}/neo4j_relationships_entity.csv' AS row
MATCH (src:Entity {{entity_id: row.`:START_ID(Entity)`}})
MATCH (dst:Entity {{entity_id: row.`:END_ID(Entity)`}})
CALL apoc.merge.relationship(
  src,
  row.`:TYPE`,
  {{relation_id: row.relation_id}},
  {{
    confidence: toFloat(row.`confidence:float`),
    support_count: toInteger(row.`support_count:int`),
    evidence_text_example: row.evidence_text_example
  }},
  dst
) YIELD rel
RETURN count(rel);

LOAD CSV WITH HEADERS FROM 'file:///{import_subdir}/neo4j_relationships_supports.csv' AS row
MATCH (src:Entity {{entity_id: row.`:START_ID(Entity)`}})
MATCH (dst:Evidence {{evidence_id: row.`:END_ID(Evidence)`}})
MERGE (src)-[r:SUPPORTED_BY {{relation_id: row.relation_id}}]->(dst);

LOAD CSV WITH HEADERS FROM 'file:///{import_subdir}/neo4j_relationships_from.csv' AS row
MATCH (src:Chunk {{chunk_id: row.`:START_ID(Chunk)`}})
MATCH (dst:Evidence {{evidence_id: row.`:END_ID(Evidence)`}})
MERGE (src)-[:FROM]->(dst);

MATCH (e:Evidence)
MATCH (c:Chunk {{chunk_id: e.chunk_id}})
MERGE (e)-[:FROM_CHUNK]->(c);

MATCH (n)
RETURN labels(n) AS labels, count(*) AS count
ORDER BY labels;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a Cypher loader for Neo4j CSV exports.")
    ap.add_argument("--csv-dir", default="data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated")
    ap.add_argument("--import-subdir", default="asd_kgrag")
    ap.add_argument("--output", default="data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher")
    args = ap.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = TEMPLATE.format(
        csv_dir=args.csv_dir,
        import_subdir=args.import_subdir.strip("/"),
        output_name=output.name,
    )
    output.write_text(text, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
