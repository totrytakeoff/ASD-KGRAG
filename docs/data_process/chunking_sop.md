# 分块 SOP（KGRAG）

## 1. 目标

将清洗后的高质量文档切分为可用于实体/关系抽取的上下文块，并确保块质量可量化、可门禁。

## 2. 输入输出

- 输入目录：`data/processed/cleaned_full`
- 输入质量筛选：`reports/clean_quality_keep_A_B.jsonl`
- 输出目录：`data/processed/chunks_full`

## 3. 分块策略

脚本：`scripts/chunking/build_context_chunks.py`

1. 仅处理 A/B 文档（默认）
2. 基于 `clean.page_texts` 恢复页级上下文
3. 标题识别与 `heading_path` 维护
4. 先段落切分，超长段按句子再切分
5. 允许跨页拼接（保持 chunk 连贯性）
6. 保留上下文字段：
   - `page_start/page_end`
   - `heading_path`
   - `prev_chunk_id/next_chunk_id`

默认参数：
- `target_tokens=520`
- `overlap_tokens=90`
- `min_tokens=180`
- `max_tokens=760`

## 4. 评估与门禁

脚本：`scripts/chunking/assess_chunk_quality.py`

门禁指标：
- `doc_coverage >= 0.99`
- `in_range_ratio >= 0.95`
- `noisy_ratio <= 0.03`
- `short_ratio <= 0.03`
- `duplicate_ratio <= 0.08`

## 5. 执行命令

```bash
python scripts/chunking/build_context_chunks.py \
  --input data/processed/cleaned_full \
  --allow-doc-ids data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl \
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

## 6. 本轮结果（2026-03-15）

- 输入文档（A/B）：441
- 输出 chunks：17,797
- 平均 chunks/doc：40.36
- token 中位数：473
- `doc_coverage = 1.0`
- `in_range_ratio = 1.0`
- `noisy_ratio = 0.002`
- `duplicate_ratio = 0.0001`
- 质量门禁：`passed = true`

下游分流：
- `chunk_quality_keep_A_B.jsonl`：17,761 块
- `chunk_quality_review_C_or_lower.jsonl`：36 块（13 文档）
