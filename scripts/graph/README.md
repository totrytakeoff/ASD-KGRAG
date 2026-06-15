# Neo4j 图谱导出与导入

## 当前导入包

当前本地 Docker 默认挂载：

```text
data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/
```

该目录是当前 KGRAG 原型使用的 Neo4j 导入基线，包含：

- `neo4j_nodes_entity.csv`
- `neo4j_nodes_chunk.csv`
- `neo4j_nodes_evidence.csv`
- `neo4j_relationships_entity.csv`
- `neo4j_relationships_supports.csv`
- `neo4j_relationships_from.csv`
- `load_current.cypher`
- `validation_queries.cypher`
- `summary.json`

当前规模：

- Entity：3684
- Chunk：7568
- Evidence：7568
- Entity relations：978

## 入口脚本

- `export_neo4j_import.py`：从 normalized JSONL 导出 Neo4j CSV
- `generate_neo4j_load_cypher.py`：生成 Cypher loader
- `write_validation_queries.py`：生成验证查询
- `annotate_graph_quality.py`：质量标注
- `apply_entity_merge_rules.py`：保守实体合并/curated alias 合并

## 本地 Neo4j

启动：

```bash
docker compose up -d
```

Browser：

- http://localhost:7474
- user: `neo4j`
- password: `asd-kgrag-local`

## 导入当前图谱

如果 Neo4j 中有旧数据，先清空：

```bash
docker exec asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  "MATCH (n) DETACH DELETE n"
```

执行导入：

```bash
docker exec -i asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  < data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher
```

执行验证：

```bash
docker exec -i asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  < data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/validation_queries.cypher
```

快速计数：

```bash
docker exec asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS count ORDER BY labels"
```

## APOC 要求

`load_current.cypher` 使用 `apoc.merge.relationship` 保留抽取关系类型，例如：

- `MEASURED_BY`
- `INDICATED_FOR`
- `COMORBID_WITH`

本仓库 `docker-compose.yml` 已启用 APOC。外部 Neo4j 需要手动安装并启用 APOC。

## 迁移建议

Neo4j 推荐迁移方式是同步导入包并重新导入，不推荐只搬 Docker volume。

完整迁移步骤见：

```text
docs/ops/database_migration.md
```
