# Graph Export Scripts

## Main script

- `export_neo4j_import.py`
  - Inputs:
    - `data/processed/normalized_full/entities.jsonl`
    - `data/processed/normalized_full/relations.jsonl`
    - `data/processed/normalized_full/evidence.jsonl`
    - `data/processed/chunks_full/chunks.jsonl`
  - Outputs:
    - `neo4j_nodes_entity.csv`
    - `neo4j_nodes_chunk.csv`
    - `neo4j_nodes_evidence.csv`
    - `neo4j_relationships_entity.csv`
    - `neo4j_relationships_supports.csv`
    - `neo4j_relationships_from.csv`

## Purpose

Prepare a flat import package for Neo4j bulk import or later Cypher-based loading.

## Current Cypher loading workflow

Generate loader and validation query files for the current revalidated export:

```bash
python scripts/graph/generate_neo4j_load_cypher.py
python scripts/graph/write_validation_queries.py
```

Outputs:

- `load_current.cypher`
- `validation_queries.cypher`

The generated loader expects CSV files to be copied into a Neo4j import
subdirectory named `asd_kgrag`.

Example:

```bash
mkdir -p "$NEO4J_HOME/import/asd_kgrag"
cp data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/*.csv \
  "$NEO4J_HOME/import/asd_kgrag/"
cp data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/*.cypher .

cypher-shell -u neo4j -p '<password>' -f load_current.cypher
cypher-shell -u neo4j -p '<password>' -f validation_queries.cypher
```

Note: the loader uses `apoc.merge.relationship` to preserve extracted relation
types such as `MEASURED_BY`, `INDICATED_FOR`, and `COMORBID_WITH`. Enable APOC in
the target Neo4j instance before running it.
