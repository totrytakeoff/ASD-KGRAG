# Embedding 与向量库

## 当前配置

- 向量库：Qdrant
- Collection：`asd_kgrag_chunks`
- Embedding 模型：`BAAI/bge-small-zh-v1.5`
- 当前 chunk 数量：`7568`

Neo4j 负责结构化图谱召回，Qdrant 负责语义相似度召回。二者通过 `chunk_id` 绑定。

## 入口脚本

- `scripts/embedding/embed_chunks.py`：chunk 文本嵌入并写入 Qdrant
- `scripts/embedding/search_chunks.py`：调试用向量搜索

## 环境变量

```bash
EMBEDDING_MODEL="BAAI/bge-small-zh-v1.5"
QDRANT_URL="http://localhost:6333"
QDRANT_COLLECTION="asd_kgrag_chunks"
QDRANT_API_KEY=""
```

## 重建 Qdrant collection

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

## 搜索验证

```bash
.venv/bin/python scripts/embedding/search_chunks.py \
  "ADOS 自闭症 诊断观察量表" \
  --collection asd_kgrag_chunks \
  --top-k 5
```

成功时会返回 top chunks 的 `chunk_id`、`title`、`year`、`evidence_level` 和 score。

## Payload 字段

当前 chunk collection payload 包含：

- `chunk_id`
- `doc_id`
- `title`
- `year`
- `evidence_level`
- `source_type`
- `heading_path`

## 迁移建议

Qdrant 推荐迁移方式是重建 collection：

1. 同步 `data/processed/chunks_extractable_full_ab_nonbook.jsonl`
2. 启动 Qdrant
3. 执行 `embed_chunks.py --recreate`
4. 执行 `search_chunks.py` 做 smoke test

不建议把 Docker volume 作为唯一迁移方式。详见 `docs/ops/database_migration.md`。
