# ASD-KGRAG

当前状态：
- 项目已完成原始提取、清洗、分块、元数据补全、实体关系抽取 pilot、归一化和 Neo4j CSV 导出验证。
- 当前处于 `7568` 条高价值主干 chunk 的批量实体关系抽取阶段。
- 最新状态记录见：`docs/status.md`

数据处理文档：
- `docs/status.md`
- `docs/data_process/extraction_dependencies.md`
- `docs/data_process/extraction_summary.md`
- `docs/data_process/requirements_extraction_system.txt`
- `docs/data_process/extraction_sop.md`
- `docs/data_process/graph_export_sop.md`
- `docs/data_process/run_log_template.md`
- `docs/data_process/source_metadata_sop.md`

脚本与依赖：
- `scripts/extraction/`
- `scripts/extraction/requirements_extraction_system.txt`
- `scripts/cleaning/`
- `scripts/metadata/`
- `scripts/chunking/`
- `scripts/graph/`

当前离线产物：
- `data/processed/extract_raw_full`
- `data/processed/cleaned_full`
- `data/processed/chunks_full`
- `data/processed/source_catalog`
- `data/processed/chunks_extractable_full_ab_nonbook.jsonl`
- `data/processed/extraction_full_ab_nonbook_v5`
- `data/processed/extraction_full_ab_nonbook_v5_retry`
- `data/processed/extraction_full_ab_nonbook_v5_merged.jsonl`
- `data/processed/extraction_full_ab_nonbook_v5_merged_revalidated.jsonl`
- `data/processed/extraction_full_ab_nonbook_v5_current_revalidated_report`
- `data/processed/normalized_full_ab_nonbook_v5_partial372`
- `data/processed/neo4j_import_full_ab_nonbook_v5_partial372`
- `data/processed/normalized_full_ab_nonbook_v5_current_revalidated`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated`

下一阶段入口：
- `scripts/extraction/run_next_extraction_batch.sh`
- `scripts/extraction/merge_extraction_runs.py`
- `scripts/extraction/revalidate_extraction_run.py`
- `scripts/extraction/summarize_extraction_run.py`
- `scripts/extraction/extract_entities_relations.py`
- `scripts/extraction/normalize_extractions.py`
- `scripts/graph/export_neo4j_import.py`
- `scripts/extraction/run_full_extraction_batches.sh`
- `scripts/extraction/rerun_timeouts_and_merge.sh`
- `scripts/extraction/entity_relation_schema.json`

推荐推进命令：

```bash
MODE=throughput bash scripts/extraction/run_next_extraction_batch.sh
```

吞吐模式用于优先扩大主干覆盖；失败 chunk 后续集中 retry。
