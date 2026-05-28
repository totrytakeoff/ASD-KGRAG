#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


QUERIES = """// ASD-KGRAG Neo4j validation queries.

// 1. Node and relationship counts.
MATCH (n)
RETURN labels(n) AS labels, count(*) AS count
ORDER BY labels;

MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(*) AS count
ORDER BY count DESC;

// 2. Top extracted entity types.
MATCH (e:Entity)
RETURN e.type AS entity_type, count(*) AS count
ORDER BY count DESC;

// 3. Screening and diagnostic tools connected to ASD/autism.
MATCH (c:Entity)-[r:MEASURED_BY]->(tool:Entity)
WHERE c.type = 'Condition'
  AND toLower(c.name) CONTAINS 'aut'
RETURN c.name AS condition,
       tool.name AS tool,
       r.support_count AS support_count,
       r.confidence AS confidence,
       r.evidence_text_example AS evidence
ORDER BY support_count DESC, confidence DESC
LIMIT 25;

// 4. Intervention targets.
MATCH (i:Entity)-[r:INDICATED_FOR]->(target:Entity)
RETURN i.name AS intervention,
       target.name AS target,
       target.type AS target_type,
       r.support_count AS support_count,
       r.evidence_text_example AS evidence
ORDER BY support_count DESC, intervention
LIMIT 25;

// 5. Evidence trace for one relation.
MATCH (src:Entity)-[r]->(dst:Entity)
WHERE type(r) IN ['MEASURED_BY', 'INDICATED_FOR', 'COMORBID_WITH']
WITH src, r, dst
ORDER BY r.support_count DESC
LIMIT 1
MATCH (src)-[s:SUPPORTED_BY {relation_id: r.relation_id}]->(ev:Evidence)-[:FROM_CHUNK]->(chunk:Chunk)
RETURN src.name AS source,
       type(r) AS relation,
       dst.name AS target,
       ev.title AS title,
       ev.year AS year,
       ev.evidence_level AS evidence_level,
       left(chunk.text, 500) AS chunk_text
LIMIT 5;

// 6. Potential noisy research modality relations for manual review.
MATCH (src:Entity)-[r:MEASURED_BY]->(tool:Entity)
WHERE any(marker IN ['EEG', 'ERP', 'MRI', 'fMRI', 'sMRI', 'fNIRS', '脑电', '磁共振']
          WHERE toLower(tool.name) CONTAINS toLower(marker))
RETURN src.name AS source,
       src.type AS source_type,
       tool.name AS tool,
       r.support_count AS support_count,
       r.evidence_text_example AS evidence
ORDER BY support_count DESC
LIMIT 50;
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Write Neo4j validation query examples.")
    ap.add_argument("--output", default="data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/validation_queries.cypher")
    args = ap.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(QUERIES, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
