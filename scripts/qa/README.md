# KGRAG QA Prototype

最小 KGRAG 问答原型：复用 Neo4j 图召回、Qdrant 向量召回和 OpenAI-compatible LLM 接口，生成带引用和安全护栏的中文回答。

## 已验证能力

- 文献证据引用：`[C1]`
- 图谱关系引用：`[G1]`
- 证据边界和临床护栏
- 批量评估：dry-run 检索评估 + 小样本真实生成评估

## 入口

CLI：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py "ADOS 是什么? 它在 ASD 评估中有什么作用?"
```

HTTP API（FastAPI / uvicorn）：

```bash
.venv/bin/python scripts/qa/kgrag_api.py --host 127.0.0.1 --port 8010
```

接口：

```bash
curl -sS http://127.0.0.1:8010/health

curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true}'
```

## 配置

脚本会自动读取项目根目录 `.env`。常用变量：

```bash
LLM_BASE_URL="https://api.siliconflow.cn/v1/chat/completions"
LLM_API_KEY="你的_key"
LLM_MODEL="deepseek-ai/DeepSeek-V4-Flash"
QA_LLM_MAX_TOKENS=1200
NEO4J_URL="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASS="asd-kgrag-local"
QDRANT_URL="http://localhost:6333"
```

## Dry Run

不调用 LLM，只验证检索、关系证据、上下文和 prompt：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 6 \
  --graph-evidence-k 4
```

API dry-run：

```bash
curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true,"context_k":4,"graph_evidence_k":2}'
```

## 批量评估

评估题集：

```bash
scripts/qa/eval_questions.jsonl
```

全量 dry-run，不调用 LLM：

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

真实生成遇到外部 LLM 瞬时网络错误时可加单题重试：

```bash
.venv/bin/python scripts/qa/evaluate_qa.py \
  --ids safety_direct_treatment safety_medication_advice \
  --context-k 6 \
  --graph-evidence-k 4 \
  --retries 1 \
  --retry-delay 3
```

端到端 smoke：

```bash
scripts/qa/e2e_check.sh
```

快速 smoke：

```bash
scripts/qa/e2e_check.sh --quick
```

包含安全/边界真实生成 smoke：

```bash
scripts/qa/e2e_check.sh --with-real
```

评估输出写入 `data/qa_eval/<timestamp>_<mode>/`：

- `summary.json`：通过率和聚合指标
- `results.jsonl`：每题的召回、回答、引用和护栏检查结果

## 当前评估基线

- dry-run：50/50 通过
- 安全/边界真实生成小样本：8/8 通过
- 评估工具版本边界真实生成小样本：5/5 通过
- 中文自然问法真实生成小样本：5/5 通过
- 检查项：上下文数量、图关系召回、期望实体词命中、回答引用、文献引用、图关系引用、临床护栏、研究边界、临床过度表述规避

## 当前流程

1. 自动从问题抽取关键词，过滤“是什么/有什么作用”等泛问题词。
2. 使用 alias map 扩展高价值查询词：`config/graph/curated_entity_alias_map.json` 只放可安全归并的实体别名，`config/qa/query_alias_map.json` 放仅用于检索扩展的版本/问卷别名。
3. Neo4j 匹配实体并扩展关系。
4. 对图谱实体做检索层降噪：去重，优先具体关键词、精确匹配、多文档实体，并按查询意图加权实体类型；例如 ADOS 优先于 ASD/孤独症这类泛词。
5. 从关系 `SUPPORTED_BY` 证据和具体实体直接证据中取 graph-evidence chunks。
6. 构造原始问题、关键词聚合、问题+关键词增强三类向量查询，合并 Qdrant 命中。
7. 合并 graph+vector 命中。
8. 构造带引用编号 `[C1]` 的证据上下文和 `[G1]` 的图谱关系上下文。
9. 对长 chunk 按关键词命中最密集区间截取，尽量保留模型实际需要的证据段。
10. 使用 `qa_usage` / `tool_category` 语义要求模型保留证据边界和临床护栏。

## 当前限制

- 关系置信度来自抽取和归一化结果，不等价于医学证据强度。
- ADOS / ADI-R / M-CHAT-R/F 等评估工具仍保留版本边界，暂不强行合并。
- 对干预、诊断、用药、风险类问题，回答必须保留“不能替代专业评估或临床决策”的限制。
- 更大 embedding 模型（如 bge-large-zh）尚未评估；当前策略是不重建 Qdrant 的轻量 query rewrite。
