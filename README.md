# ASD-KGRAG

ASD 领域知识图谱 RAG 系统：文档 → 清洗 → 分块 → 实体关系抽取 → Neo4j 图谱 + Qdrant 向量库 → 混合检索 → 问答。

## 当前进度

| 阶段 | 进度 |
|------|------|
| 数据提取 | 100% |
| 清洗 | 100% |
| 分块 | 100% |
| 元数据补全 | 100% |
| 实体关系抽取 | 100% (7568/7568) |
| 归一化 + Neo4j 入库 | 100% |
| Embedding + Qdrant | 100% |
| 混合检索原型 | 100% |
| KGRAG 问答原型 | 90% |

状态详情：`docs/status.md`

## 快速启动

### 1. 准备配置

```bash
cp .env.example .env
```

编辑 `.env`，至少填入：

```bash
LLM_API_KEY="你的_key"
```

如果只跑 dry-run 检索验证，可以暂时不填 `LLM_API_KEY`。

### 2. 启动数据库服务

```bash
docker compose up -d
docker compose ps
```

本地服务：

| 服务 | 地址 | 说明 |
|------|------|------|
| Neo4j Browser | http://localhost:7474 | `neo4j / asd-kgrag-local` |
| Neo4j Bolt | bolt://localhost:7687 | 图谱查询 |
| Qdrant REST | http://localhost:6333 | 向量库 |

### 3. 验证 KGRAG 检索链路

不调用 LLM，只验证 Neo4j + Qdrant + prompt 构造：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 4 \
  --graph-evidence-k 2
```

### 4. 运行真实问答

需要 `.env` 中配置有效 `LLM_API_KEY`：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --context-k 4 \
  --graph-evidence-k 2
```

### 5. 启动 HTTP API

```bash
.venv/bin/python scripts/qa/kgrag_api.py --host 127.0.0.1 --port 8010
```

另开终端验证：

```bash
curl -sS http://127.0.0.1:8010/health

curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true,"context_k":4,"graph_evidence_k":2}'
```

### 6. 批量评估

```bash
.venv/bin/python scripts/qa/evaluate_qa.py --dry-run --context-k 6 --graph-evidence-k 4
```

真实生成小样本：

```bash
.venv/bin/python scripts/qa/evaluate_qa.py \
  --ids assessment_ados intervention_aba comorbidity_sleep safety_direct_treatment \
  --context-k 4 \
  --graph-evidence-k 2
```

## 数据资产

`data/` 不进入 git。新机器只拉代码不能完整运行，需要额外同步数据资产。

最低运行所需数据：

| 用途 | 路径 |
|------|------|
| Neo4j 导入包 | `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/` |
| Qdrant 重建输入 | `data/processed/chunks_extractable_full_ab_nonbook.jsonl` |
| 本地备份 | `data/backups/` |
| 学生返还文件 | `data/student_returns/` |

详见：`docs/ops/data_assets.md`

## 数据库迁移

推荐迁移方式：

- Neo4j：同步 CSV/Cypher 导入包，在目标机器重新导入。
- Qdrant：同步 chunk JSONL，在目标机器重新 embedding 写入 collection。

详见：

- `docs/ops/database_migration.md`
- `docs/ops/backup_restore.md`

## 目录结构

- `scripts/extraction/` 数据提取、实体关系抽取、归一化
- `scripts/embedding/` embedding 写入与搜索
- `scripts/retrieval/` 混合检索
- `scripts/qa/` KGRAG CLI/API 问答与评估
- `scripts/graph/` Neo4j 导出、Cypher 生成、图谱质量处理
- `scripts/cleaning/` 数据清洗
- `scripts/chunking/` 分块
- `scripts/metadata/` 元数据补全
- `docs/ops/` 运行、迁移、备份、排障文档
- `docs/tasks/` 学生协作任务文档和模板
- `docker-compose.yml` Neo4j + Qdrant

## 关键文档

- 快速启动：`docs/ops/quickstart.md`
- 数据资产：`docs/ops/data_assets.md`
- 数据库迁移：`docs/ops/database_migration.md`
- 备份恢复：`docs/ops/backup_restore.md`
- 排障：`docs/ops/troubleshooting.md`
- QA 使用：`scripts/qa/README.md`
- 图谱导入：`scripts/graph/README.md`
- 向量库：`scripts/embedding/README.md`
