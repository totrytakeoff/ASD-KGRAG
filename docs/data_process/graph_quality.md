# Graph Quality Pass

更新时间：2026-06-08

## 目标

本轮质量处理不直接删除或强行合并原始实体，而是在 normalized 和 Neo4j 层增加可审计的质量标注，便于后续筛选、人工复核、KGRAG 回答护栏和下一轮实体归并。

## 新增产物

- `scripts/graph/annotate_graph_quality.py`
- `data/processed/normalized_full_ab_nonbook_v5_current_quality/`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_quality/`

当前 Neo4j 挂载目录 `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/` 已同步为质量增强版导出。

## 标注字段

Entity 新增：

- `quality_flags`
- `is_isolated`
- `graph_degree`
- `duplicate_group_key`
- `duplicate_group_size`
- `merge_candidate_types`
- `conflict_aliases`
- `tool_category`

Relation 新增：

- `quality_flags`
- `qa_usage`
- `evidence_level_summary`
- `src_type`
- `dst_type`

## 当前质量概览

Entity：

- 总数：3706
- 孤立实体：2812
- 同名重复实体组：138
- 别名跨类型冲突实体：416
- 单 chunk 实体：2523

AssessmentTool 分类：

- `clinical_assessment`：192
- `unspecified_assessment`：224
- `generic_method`：38
- `research_modality`：18
- `digital_algorithm`：13

Relation：

- 总数：987
- `guardrailed_clinical_context`：577
- `use_with_caution`：331
- `research_context_only`：43
- `standard`：36

主要 relation flags：

- `single_evidence_relation`：802
- `low_confidence`：671
- `clinical_answer_requires_evidence_guardrail`：577
- `measurement_tool_category:generic_method`：19
- `measurement_tool_category:research_modality`：17
- `measurement_tool_category:digital_algorithm`：7

## Neo4j Browser 查询

查看孤立实体：

```cypher
MATCH (e:Entity)
WHERE e.is_isolated = true
RETURN e.name, e.type, e.source_chunk_count, e.quality_flags
ORDER BY e.source_chunk_count DESC
LIMIT 50;
```

查看同名/别名冲突实体：

```cypher
MATCH (e:Entity)
WHERE 'alias_type_conflict' IN e.quality_flags
RETURN e.duplicate_group_key, e.name, e.type, e.merge_candidate_types, e.conflict_aliases
ORDER BY e.duplicate_group_key
LIMIT 80;
```

查看研究模态或算法类测量关系：

```cypher
MATCH p=(src:Entity)-[r:MEASURED_BY]->(tool:Entity)
WHERE r.qa_usage = 'research_context_only'
RETURN p
LIMIT 50;
```

查看需要临床回答护栏的干预关系：

```cypher
MATCH p=(i:Entity)-[r:INDICATED_FOR]->(target:Entity)
WHERE r.qa_usage = 'guardrailed_clinical_context'
RETURN p
LIMIT 50;
```

查看标准关系：

```cypher
MATCH p=(src:Entity)-[r]->(dst:Entity)
WHERE r.qa_usage = 'standard'
RETURN p
LIMIT 50;
```

## 后续建议

1. 对 `alias_type_conflict` 和 `same_name_duplicate` 做人工抽样，确定可自动合并的类型优先级规则。
2. 将 `tool_category` 用于 KGRAG 回答策略：临床筛查工具可以直接用于“评估工具”回答，研究模态和算法工具只能作为研究背景。
3. 将 `qa_usage` 用于问答护栏：干预类回答必须带证据说明，不直接生成医疗建议。
