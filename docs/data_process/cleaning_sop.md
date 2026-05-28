# 数据清洗 SOP（KGRAG）

## 1. 目标

将 `extract_raw_full` 的原始提取文本清洗为可用于 KGRAG 的高可读上下文文本，并提供可量化质量门禁。

## 2. 输入输出

- 输入目录：`data/processed/extract_raw_full`
- 清洗输出：`data/processed/cleaned_full`
- 评估报告：`data/processed/cleaned_full/reports`

## 3. 清洗规则（当前版本）

脚本：`scripts/cleaning/clean_extracted_corpus.py`

1. 行级标准化
- 统一空白字符（tab/NBSP/null）
- 压缩多空格

2. 噪声删除
- 删除纯符号行、页码行、已知元数据噪声行
- 删除高概率 OCR 噪声行（短 token 密集 + 异常符号）

3. 重复页眉页脚删除
- 跨页统计短行频次，按阈值删除高频重复行

4. OCR 空格修复
- 中文字间断裂修复：`神 经` -> `神经`
- 中文标点前后空格修复
- 中文语境下 ASCII 标点空格修复
- 英文单词字母断裂修复：`N e u r o n` -> `Neuron`

5. 上下文保留
- 保留 `[PAGE n]` 分页标记
- 保留 `clean.page_texts`（页级文本）

6. 参考文献尾部裁剪
- 命中 `参考文献/References/Bibliography` 且位于后 60% 区域时截断

## 4. 评估指标与门禁

脚本：`scripts/cleaning/assess_clean_quality.py`

核心指标：
- `pass_rate_B_or_above`
- `cjk_space_ratio`（中文断裂空格）
- `noisy_line_ratio`（噪声行比例）
- `ratio_docs_cjk_space_gt_0_20`
- `f_grade_ratio`

质量门禁（当前阈值）：
- `pass_rate_B_or_above >= 0.90`
- `p95_cjk_space_ratio <= 0.08`
- `ratio_docs_cjk_space_gt_0_20 <= 0.05`
- `p95_noisy_line_ratio <= 0.12`
- `f_grade_ratio <= 0.03`

## 5. 执行命令

```bash
python scripts/cleaning/clean_extracted_corpus.py \
  --input data/processed/extract_raw_full \
  --output data/processed/cleaned_full \
  --workers 10

python scripts/cleaning/assess_clean_quality.py \
  --input data/processed/cleaned_full \
  --sample-size 30 \
  --seed 42
```

## 6. 本轮结果（2026-03-15）

- 总文档：456
- 评分分布：A=439, B=2, C=11, D=4, F=0
- `pass_rate_B_or_above = 0.9671`
- `p95_cjk_space_ratio = 0.0`
- `p95_noisy_line_ratio = 0.0455`
- 质量门禁：`passed = true`

下游分流：
- 可直接入库（A/B）：441 篇
- 待复核（C/D/F）：15 篇

对应文件：
- `reports/clean_quality_keep_A_B.jsonl`
- `reports/clean_quality_review_C_or_lower.jsonl`
- `reports/review_rerun_list.txt`
