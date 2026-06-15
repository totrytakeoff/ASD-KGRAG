# 常见问题排查

## 1. `docker compose ps` 看不到服务

启动：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs neo4j
docker compose logs qdrant
```

确认端口没有被占用：

```bash
ss -ltnp | grep -E '7474|7687|6333|6334'
```

## 2. Neo4j Browser 打不开

检查：

```bash
docker compose ps
```

访问：

```text
http://localhost:7474
```

账号：

```text
neo4j / asd-kgrag-local
```

如果认证失败，确认 `docker-compose.yml` 中 `NEO4J_AUTH` 是否被改过。

## 3. Neo4j 里没有数据

执行计数：

```bash
docker exec asd-kgrag-neo4j cypher-shell \
  -u neo4j -p asd-kgrag-local \
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS count ORDER BY labels"
```

如果为空，按以下文档恢复：

```text
docs/ops/database_migration.md
```

## 4. Neo4j 导入报 `apoc` 相关错误

当前 loader 使用 `apoc.merge.relationship`。

确认 compose 中有：

```yaml
NEO4J_PLUGINS: '["apoc"]'
NEO4J_dbms_security_procedures_unrestricted: "apoc.*"
NEO4J_dbms_security_procedures_allowlist: "apoc.*"
```

如果是外部 Neo4j，需要安装并启用 APOC。

## 5. Qdrant 搜索失败

确认 Qdrant 服务：

```bash
curl -sS http://localhost:6333/collections
```

如果没有 `asd_kgrag_chunks`，重建：

```bash
.venv/bin/python scripts/embedding/embed_chunks.py \
  --input data/processed/chunks_extractable_full_ab_nonbook.jsonl \
  --collection asd_kgrag_chunks \
  --model BAAI/bge-small-zh-v1.5 \
  --qdrant-url http://localhost:6333 \
  --batch-size 64 \
  --recreate
```

## 6. QA dry-run 报找不到数据文件

常见原因：

- 没有同步 `data/`。
- 路径解压错了。
- 只 clone 了 git 仓库。

最低需要：

```text
data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/
data/processed/chunks_extractable_full_ab_nonbook.jsonl
```

详见：

```text
docs/ops/data_assets.md
```

## 7. 真实 QA 报 API key 缺失

dry-run 不需要 API key，真实生成需要。

检查 `.env`：

```bash
LLM_API_KEY="你的_key"
LLM_BASE_URL="https://api.siliconflow.cn/v1/chat/completions"
LLM_MODEL="deepseek-ai/DeepSeek-V4-Flash"
```

验证 dry-run：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么?" \
  --dry-run
```

## 8. 真实 QA 很慢

常见原因：

- LLM 接口响应慢。
- 首次加载 embedding 模型慢。
- CPU embedding 速度有限。

处理：

- 先用 `--dry-run` 判断检索是否正常。
- 小样本真实生成，不要一次跑太多。
- 批量评估优先使用 `--dry-run`。

## 9. API 端口 8010 被占用

换端口：

```bash
.venv/bin/python scripts/qa/kgrag_api.py --host 127.0.0.1 --port 8011
```

或者查占用：

```bash
ss -ltnp | grep 8010
```

## 10. 不要执行的危险操作

不要随便执行：

```bash
docker compose down -v
```

它会删除 Neo4j/Qdrant volume。除非你确认已经有导入包和 chunk JSONL，可以重新恢复。
