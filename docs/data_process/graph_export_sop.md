# Graph Export SOP

## Goal

Convert normalized extraction outputs into Neo4j-ready CSV files.

## Workflow

1. Normalize raw extraction results:

```bash
python scripts/extraction/normalize_extractions.py \
  --input data/processed/extraction_full/chunk_extractions.jsonl \
  --output data/processed/normalized_full
```

2. Export Neo4j import files:

```bash
python scripts/graph/export_neo4j_import.py \
  --entities data/processed/normalized_full/entities.jsonl \
  --relations data/processed/normalized_full/relations.jsonl \
  --evidence data/processed/normalized_full/evidence.jsonl \
  --chunks data/processed/chunks_full/chunks.jsonl \
  --output data/processed/neo4j_import
```

## Main outputs

- `neo4j_nodes_entity.csv`
- `neo4j_nodes_chunk.csv`
- `neo4j_nodes_evidence.csv`
- `neo4j_relationships_entity.csv`
- `neo4j_relationships_supports.csv`
- `neo4j_relationships_from.csv`
