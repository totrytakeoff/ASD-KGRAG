# 备份与恢复

本文档说明 ASD-KGRAG 本地开发环境的备份和恢复策略。

## 备份原则

优先备份可重建的中间资产：

- Neo4j CSV/Cypher 导入包
- Qdrant 重建输入 chunk JSONL
- 关键配置模板和文档

Docker volume 可以备份，但不作为唯一备份。

## 最小运行备份

生成最小运行数据包：

```bash
mkdir -p data/backups

tar -czf data/backups/asd_kgrag_min_runtime_data_YYYYMMDD.tar.gz \
  data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated \
  data/processed/chunks_extractable_full_ab_nonbook.jsonl
```

这个包足够在另一台机器上重建：

- Neo4j 图谱
- Qdrant chunk collection

## 完整处理结果备份

如果要保留更多中间结果：

```bash
mkdir -p data/backups

tar -czf data/backups/asd_kgrag_processed_data_YYYYMMDD.tar.gz \
  data/processed \
  data/qa_eval
```

注意：这个包可能很大。

## `.env` 备份

`.env` 含有 API key，不进入 git。

如果需要迁移到另一台自己的机器，可以手动复制：

```bash
cp .env data/backups/env.local.YYYYMMDD
```

不要把这个文件发给其他人，不要提交 git。

## Neo4j 恢复

推荐恢复方式见：

```text
docs/ops/database_migration.md
```

核心步骤：

```bash
docker compose up -d

docker exec asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  "MATCH (n) DETACH DELETE n"

docker exec -i asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  < data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher
```

然后运行 validation queries。

## Qdrant 恢复

推荐从 chunk JSONL 重建：

```bash
.venv/bin/python scripts/embedding/embed_chunks.py \
  --input data/processed/chunks_extractable_full_ab_nonbook.jsonl \
  --collection asd_kgrag_chunks \
  --model BAAI/bge-small-zh-v1.5 \
  --qdrant-url http://localhost:6333 \
  --batch-size 64 \
  --recreate
```

## Docker volume 快速备份

查看 volume：

```bash
docker volume ls | grep asd-kgrag
```

当前 compose 使用：

```text
asd-kgrag_neo4j_data
asd-kgrag_neo4j_logs
asd-kgrag_qdrant_data
```

不同 Docker Compose 版本可能给 volume 加不同项目前缀，以 `docker volume ls` 实际输出为准。

volume 备份更适合同机恢复。跨机器迁移仍推荐导入包重建。

## 恢复后验收

执行：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 4 \
  --graph-evidence-k 2
```

验收：

- 能连 Neo4j。
- 能连 Qdrant。
- 能返回 contexts 和 relations。
- dry-run 不报错。
