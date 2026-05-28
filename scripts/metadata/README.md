# Source Metadata Scripts

## Main script

- `build_source_catalog.py`
  - Inputs:
    - `data/processed/cleaned_full/manifest.jsonl`
    - `data/processed/cleaned_full/docs/*.json`
  - Outputs:
    - `data/processed/source_catalog/source_metadata.jsonl`
    - `data/processed/source_catalog/source_metadata.csv`
    - `data/processed/source_catalog/summary.json`
  - Purpose:
    - Build a doc-level metadata catalog for KGRAG, including `title`, `year`, `source_type`, `evidence_level`, and `include_flag`.

## Recommended command

```bash
python scripts/metadata/build_source_catalog.py \
  --manifest data/processed/cleaned_full/manifest.jsonl \
  --docs-root data/processed/cleaned_full/docs \
  --output data/processed/source_catalog
```

## Notes

- The default heuristic is intentionally conservative.
- `source_type` and `evidence_level` should be reviewed later for high-value docs such as guidelines and systematic reviews.
- `build_context_chunks.py` can read the generated JSONL via `--source-metadata`.
