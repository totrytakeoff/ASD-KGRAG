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
