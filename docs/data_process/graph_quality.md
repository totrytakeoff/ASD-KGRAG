# Graph Quality Pass

更新时间：2026-06-08

## 目标

本轮质量处理分两步：

1. 在 normalized 和 Neo4j 层增加可审计的质量标注，便于后续筛选、人工复核、KGRAG 回答护栏和下一轮实体归并。
2. 对同类型同名实体执行保守合并，只处理低风险类型，避免把年龄阶段、场景、机制、任务等语义边界敏感实体误合并。

## 新增产物

- `scripts/graph/annotate_graph_quality.py`
- `scripts/graph/apply_entity_merge_rules.py`
- `data/processed/normalized_full_ab_nonbook_v5_current_quality/`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_quality/`
- `data/processed/normalized_full_ab_nonbook_v5_current_curated_base/`
- `data/processed/normalized_full_ab_nonbook_v5_current_curated_quality/`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_curated_quality/`

当前 Neo4j 挂载目录 `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/` 已同步为保守合并后的质量增强版导出。

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

- 总数：3688
- 孤立实体：2800
- 同名重复实体组：121
- 别名跨类型冲突实体：414
- 单 chunk 实体：2514

AssessmentTool 分类：

- `clinical_assessment`：189
- `unspecified_assessment`：224
- `generic_method`：38
- `research_modality`：18
- `digital_algorithm`：13

Relation：

- 总数：980
- `guardrailed_clinical_context`：574
- `use_with_caution`：329
- `research_context_only`：43
- `standard`：34

主要 relation flags：

- `single_evidence_relation`：799
- `low_confidence`：666
- `clinical_answer_requires_evidence_guardrail`：574
- `measurement_tool_category:generic_method`：19
- `measurement_tool_category:research_modality`：17
- `measurement_tool_category:digital_algorithm`：7

## 保守合并结果

合并范围：

- 允许合并：`AssessmentTool`、`Intervention`、`Condition`、`Symptom`、`Comorbidity`、`Risk`
- 暂不合并：`AgeStage`、`Setting`、`Mechanism`、`Task`

结果：

- 输入 Entity：3706
- 输出 Entity：3688
- 减少 Entity：18
- Merge group：18
- 输入 Relation：987
- 输出 Relation：980
- 减少 Relation：7

合并示例：

- AssessmentTool：M-CHAT、SRS、AQ-Adult
- Intervention：音乐治疗、感觉统合训练、催产素、骑马训练
- Symptom/Condition/Risk：睡眠问题、破坏性行为、情绪识别障碍、低功能孤独症、adverse events

重要修正：

- 初版尝试曾把 `AgeStage` 中的“儿童”等实体纳入合并候选，风险较高。
- 当前脚本已收紧为 `DEFAULT_MERGE_TYPES` 白名单，只合并低风险类型。
- `annotate_graph_quality.py` 会保留人工/上游质量标记，并只刷新脚本派生的质量标记，避免重跑标注时丢失 `merged_same_type_same_name`。

## 当前 Neo4j 状态

Neo4j Browser：

- URL：`http://localhost:7474`
- 用户：`neo4j`
- 密码：`asd-kgrag-local`

节点：

- `Chunk`：7568
- `Entity`：3688
- `Evidence`：7568

关系：

- `FROM`：7568
- `FROM_CHUNK`：7568
- `SUPPORTED_BY`：1702
- `INDICATED_FOR`：534
- `MEASURED_BY`：253
- `COMORBID_WITH`：83
- `SUITABLE_AGE`：43
- `HAS_RISK`：32
- `SUITABLE_SETTING`：27
- `NOT_INDICATED_FOR`：8

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

查看已保守合并的实体：

```cypher
MATCH (e:Entity)
WHERE 'merged_same_type_same_name' IN e.quality_flags
RETURN e.type, e.name, e.source_chunk_count, e.synonyms[..8]
ORDER BY e.source_chunk_count DESC
LIMIT 50;
```

查看剩余同名重复组：

```cypher
MATCH (e:Entity)
WHERE 'same_name_duplicate' IN e.quality_flags
RETURN e.duplicate_group_key, collect(DISTINCT e.type) AS types, count(*) AS entities
ORDER BY entities DESC
LIMIT 50;
```

## 后续建议

1. 对剩余 `same_name_duplicate` 和 `alias_type_conflict` 做高价值抽样，不再扩大无差别自动合并范围。
2. 优先补充 ASD 核心概念、评估工具、干预手段的 curated alias map。
3. 将 `tool_category` 用于 KGRAG 回答策略：临床筛查工具可以直接用于“评估工具”回答，研究模态和算法工具只能作为研究背景。
4. 将 `qa_usage` 用于问答护栏：干预类回答必须带证据说明，不直接生成医疗建议。
