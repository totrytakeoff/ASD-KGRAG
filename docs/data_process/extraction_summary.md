# 数据提取结果总结（最终版）

详细执行流程（逐步命令 + 验收 + 故障处理）见：
- `docs/data_process/extraction_sop.md`
- `docs/data_process/run_log_template.md`

## 1) 结果概览

最终目录：`data/processed/extract_raw_full`

关键统计：
- 总文档：`456`
- 提取成功：`456`
- 失败：`0`
- 提取来源：
  - `textlayer`: `418`
  - `ocr`: `37`
  - `docx`: `1`

见：`data/processed/extract_raw_full/summary.json`

## 2) 质量评估

见：`data/processed/extract_raw_full/reports/quality_summary.json`

核心指标：
- `A`: 374
- `B`: 40
- `C`: 41
- `D`: 1
- `F`: 0
- `pass_rate_B_or_above`: 90.79%
- `pass_rate_C_or_above`: 99.78%

解释：
- 已达到可用于 KGRAG 构建的可用标准。
- 少量 `partial_coverage` 文档属于“部分页 OCR”策略带来的覆盖不足，后续可按需补扫。

## 3) 输出结构（对 KGRAG 友好）

每个文档 JSON 包含：
- `extract.textlayer.page_texts`（页级文本）
- `extract.ocr.page_texts`（OCR 页级文本）
- `extract.merged.page_texts`（最终采用页级文本）
- `extract.merged.selected_source`（`textlayer|ocr|docx`）
- `extract.merged.extraction_coverage_ratio`

这些字段可直接用于：
- 实体抽取时的页级回溯
- 证据定位与引用
- 后续 chunk 切分与上下文拼接

## 4) 下一步（进入清洗）

建议清洗顺序：
1. 去元信息噪声（版权页、目录密集页）
2. 参考文献区切除或降权
3. 页内断行修复与段落合并
4. 结构化切分（按标题/页+token）
5. 生成 `chunk_id + prev/next + heading_path + page_span`

建议先从 `C` 级文档开始抽样调参，再全量清洗。
