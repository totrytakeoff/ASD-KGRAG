# Chunking Scripts

## 主要脚本

- `build_context_chunks.py`
  - 输入：`data/processed/cleaned_full/docs/*.json`
  - 默认仅处理 A/B 文档：`clean_quality_keep_A_B.jsonl`
  - 可选读取：`data/processed/source_catalog/source_metadata.jsonl`
  - 输出：`data/processed/chunks_full/chunks.jsonl`

- `assess_chunk_quality.py`
  - 输入：`data/processed/chunks_full/chunks.jsonl`
  - 输出：`data/processed/chunks_full/reports/*`
  - 提供质量门禁与分流文件（A/B 保留、C/D 复核）

## 推荐命令

```bash
python scripts/chunking/build_context_chunks.py \
  --input data/processed/cleaned_full \
  --allow-doc-ids data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl \
  --source-metadata data/processed/source_catalog/source_metadata.jsonl \
  --output data/processed/chunks_full \
  --target-tokens 520 \
  --overlap-tokens 90 \
  --min-tokens 180 \
  --max-tokens 760

python scripts/chunking/assess_chunk_quality.py \
  --input data/processed/chunks_full \
  --expected-doc-ids data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl \
  --min-tokens 180 \
  --max-tokens 760 \
  --sample-size 30
```

## 关键产物

- `data/processed/chunks_full/chunks.jsonl`
- `data/processed/chunks_full/doc_chunk_map.json`
- `data/processed/chunks_full/summary.json`
- `data/processed/chunks_full/reports/chunk_quality_summary.json`
- `data/processed/chunks_full/reports/chunk_quality_keep_A_B.jsonl`
- `data/processed/chunks_full/reports/chunk_quality_review_C_or_lower.jsonl`
- 关键附加字段：`title/year/source_type/evidence_level/include_flag/language`
