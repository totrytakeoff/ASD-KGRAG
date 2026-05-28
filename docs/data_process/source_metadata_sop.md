# Source Metadata SOP

## Goal

Build a stable doc-level catalog so downstream chunking, extraction, graph loading, and evaluation all use the same metadata keys.

## Output fields

- `doc_id`
- `relative_path`
- `source_group`
- `title`
- `year`
- `language`
- `source_type`
- `evidence_level`
- `include_flag`
- `license`
- `url`
- `notes`

## Recommended workflow

1. Generate the initial catalog:

```bash
python scripts/metadata/build_source_catalog.py \
  --manifest data/processed/cleaned_full/manifest.jsonl \
  --docs-root data/processed/cleaned_full/docs \
  --output data/processed/source_catalog
```

2. Review the following high-impact fields for important documents:
- `year`
- `source_type`
- `evidence_level`
- `include_flag`

3. Rebuild chunks with source metadata attached:

```bash
python scripts/chunking/build_context_chunks.py \
  --input data/processed/cleaned_full \
  --allow-doc-ids data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl \
  --source-metadata data/processed/source_catalog/source_metadata.jsonl \
  --output data/processed/chunks_full
```

## Notes

- The first pass uses filename and text heuristics, so it is a bootstrap catalog rather than a final curated source registry.
- `evidence_level` is intended for retrieval weighting and safety constraints later in the KGRAG pipeline.
