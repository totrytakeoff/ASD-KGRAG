# 快速启动

本文档说明如何在本地启动 ASD-KGRAG，并验证 Neo4j、Qdrant、KGRAG QA 链路。

## 1. 前置条件

需要：

- Docker / Docker Compose
- Python 3.10+
- 已准备好的 `.venv`
- 已同步 `data/` 目录中的必要数据资产

当前项目没有把 `data/` 提交到 git。新机器只 clone 代码是不够的。

最低需要同步：

```text
data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/
data/processed/chunks_extractable_full_ab_nonbook.jsonl
```

如果目标机器已经有 Neo4j/Qdrant volume，也可以不重建数据库，但仍建议保留这些可重建数据。

## 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
LLM_API_KEY="你的_key"
```

只跑 dry-run 时可以不填 key。

常用默认值：

```bash
NEO4J_URL="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASS="asd-kgrag-local"
QDRANT_URL="http://localhost:6333"
QDRANT_COLLECTION="asd_kgrag_chunks"
EMBEDDING_MODEL="BAAI/bge-small-zh-v1.5"
```

## 3. 启动数据库服务

```bash
docker compose up -d
docker compose ps
```

应看到：

```text
asd-kgrag-neo4j
asd-kgrag-qdrant
```

访问：

- Neo4j Browser: http://localhost:7474
- Qdrant REST: http://localhost:6333

Neo4j 默认账号：

```text
neo4j / asd-kgrag-local
```

## 4. 如果数据库为空，先恢复数据

Neo4j 和 Qdrant 恢复步骤见：

```text
docs/ops/database_migration.md
```

简要判断：

- 如果 Neo4j Browser 能看到 Entity/Chunk/Evidence 节点，Neo4j 已有数据。
- 如果 Qdrant collection `asd_kgrag_chunks` 存在且有 7568 points，Qdrant 已有数据。

## 5. 验证 CLI dry-run

dry-run 不调用 LLM，只验证检索、图关系、证据上下文和 prompt：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 4 \
  --graph-evidence-k 2
```

成功时应输出：

- query
- keywords
- graph counts
- top contexts
- prompt preview

## 6. 验证真实生成

需要 `.env` 有可用 `LLM_API_KEY`：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --context-k 4 \
  --graph-evidence-k 2
```

成功回答应包含：

- 中文结构化回答
- `[C*]` 文献引用
- `[G*]` 图谱关系引用
- 诊断/干预相关护栏

## 7. 启动 HTTP API

```bash
.venv/bin/python scripts/qa/kgrag_api.py --host 127.0.0.1 --port 8010
```

验证：

```bash
curl -sS http://127.0.0.1:8010/health
```

dry-run 请求：

```bash
curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true,"context_k":4,"graph_evidence_k":2}'
```

真实生成请求：

```bash
curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","context_k":4,"graph_evidence_k":2}'
```

## 8. 批量评估

全量 dry-run：

```bash
.venv/bin/python scripts/qa/evaluate_qa.py --dry-run --context-k 6 --graph-evidence-k 4
```

小样本真实生成：

```bash
.venv/bin/python scripts/qa/evaluate_qa.py \
  --ids assessment_ados intervention_aba comorbidity_sleep safety_direct_treatment \
  --context-k 4 \
  --graph-evidence-k 2
```

输出在：

```text
data/qa_eval/<timestamp>_<mode>/
```

## 9. 停止服务

```bash
docker compose stop
```

如果要删除容器但保留 volume：

```bash
docker compose down
```

不要随便执行 `docker compose down -v`，它会删除 Neo4j/Qdrant 本地 volume。
