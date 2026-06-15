# 数据库迁移

本文档说明如何把 ASD-KGRAG 的 Neo4j 图数据库和 Qdrant 向量库迁移到另一台机器。

推荐策略：

- Neo4j：迁移 CSV/Cypher 导入包，然后重新导入。
- Qdrant：迁移 chunk JSONL，然后重新 embedding 写入 collection。

不推荐把 Docker volume 作为唯一迁移方式。volume 适合同机备份或快速回滚，但跨机器可复现性不如导入包。

---

## 1. 迁移前准备

在源机器打包最低运行数据：

```bash
tar -czf asd_kgrag_min_runtime_data_YYYYMMDD.tar.gz \
  data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated \
  data/processed/chunks_extractable_full_ab_nonbook.jsonl
```

把压缩包和代码仓库同步到目标机器。

目标机器解压到项目根目录：

```bash
tar -xzf asd_kgrag_min_runtime_data_YYYYMMDD.tar.gz
```

确认文件存在：

```bash
test -f data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher
test -f data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/validation_queries.cypher
test -f data/processed/chunks_extractable_full_ab_nonbook.jsonl
```

---

## 2. 启动目标数据库服务

```bash
docker compose up -d
docker compose ps
```

Neo4j:

```text
http://localhost:7474
neo4j / asd-kgrag-local
```

Qdrant:

```text
http://localhost:6333
```

---

## 3. 恢复 Neo4j

当前 `docker-compose.yml` 已将导入包挂载到容器内：

```text
./data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated:/import/asd_kgrag:ro
```

### 3.1 可选：清空旧图

如果目标 Neo4j 里已经有旧数据，先清空：

```bash
docker exec asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  "MATCH (n) DETACH DELETE n"
```

### 3.2 执行导入

```bash
docker exec -i asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  < data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher
```

### 3.3 执行验证

```bash
docker exec -i asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  < data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/validation_queries.cypher
```

### 3.4 预期规模

导入后应接近：

| 类型 | 数量 |
|------|------|
| Entity | 3684 |
| Chunk | 7568 |
| Evidence | 7568 |
| Entity relations | 978 |

也可以手动查询：

```bash
docker exec asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS count ORDER BY labels"
```

---

## 4. 恢复 Qdrant

推荐从 chunk JSONL 重建 collection。

### 4.1 重建 collection

```bash
.venv/bin/python scripts/embedding/embed_chunks.py \
  --input data/processed/chunks_extractable_full_ab_nonbook.jsonl \
  --collection asd_kgrag_chunks \
  --model BAAI/bge-small-zh-v1.5 \
  --qdrant-url http://localhost:6333 \
  --batch-size 64 \
  --recreate
```

预期写入：

```text
7568 vectors
```

### 4.2 搜索验证

```bash
.venv/bin/python scripts/embedding/search_chunks.py \
  "ADOS 自闭症 诊断观察量表" \
  --collection asd_kgrag_chunks \
  --top-k 5
```

如果能返回 chunk_id/title/score，说明 Qdrant 可用。

---

## 5. KGRAG smoke test

dry-run：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 4 \
  --graph-evidence-k 2
```

预期：

- 有 graph counts。
- 有 contexts。
- 有 relations。
- prompt preview 中包含 `[C*]` 和 `[G*]` 引用上下文。

真实生成：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --context-k 4 \
  --graph-evidence-k 2
```

需要 `.env` 中有有效 `LLM_API_KEY`。

---

## 6. Docker volume 迁移说明

Neo4j 和 Qdrant 的 Docker volume：

```text
neo4j_data
neo4j_logs
qdrant_data
```

volume 适合：

- 同一台机器快速备份。
- Docker 环境一致的快速恢复。

不适合：

- 作为唯一长期备份。
- 跨系统、跨架构迁移。
- 交给其他同学复现。

跨机器迁移优先使用本文档的“导入包 + 重建 collection”方式。
