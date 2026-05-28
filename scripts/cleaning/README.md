# Cleaning Scripts

## 主要脚本

- `clean_extracted_corpus.py`
  - 输入：`data/processed/extract_raw_full/docs/*.json`
  - 输出：`data/processed/cleaned_full/`
  - 作用：清理 OCR 间隔空格、标点空格、重复页眉页脚、噪声行，保留分页上下文。

- `assess_clean_quality.py`
  - 输入：`data/processed/cleaned_full/docs/*.json`
  - 输出：`data/processed/cleaned_full/reports/*`
  - 作用：按质量指标评分并产出 `A/B 保留` 与 `C/D/F 复核` 列表。

- `parse_clean_corpus.py`
  - 历史版本清洗脚本，保留用于追溯。

## 推荐流程

1. 执行清洗：
   - `python scripts/cleaning/clean_extracted_corpus.py --input data/processed/extract_raw_full --output data/processed/cleaned_full --workers 10`
2. 执行评估：
   - `python scripts/cleaning/assess_clean_quality.py --input data/processed/cleaned_full --sample-size 30 --seed 42`
3. 查看质量门禁与分流文件：
   - `data/processed/cleaned_full/reports/clean_quality_summary.json`
   - `data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl`
   - `data/processed/cleaned_full/reports/clean_quality_review_C_or_lower.jsonl`
