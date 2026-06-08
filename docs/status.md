# 项目状态记录

更新时间：2026-06-08

## 总体进度

| 阶段 | 进度 | 状态 |
|------|------|------|
| 1. 数据提取 | 100% | 已完成 |
| 2. 数据清洗 | 100% | 已完成 |
| 3. 分块 | 100% | 已完成 |
| 4. 元数据补全 | 100% | 已完成 |
| 5. 实体关系抽取 | 100% | 全量抽取 + 两轮失败重试已完成（7568/7568 成功，0 失败） |
| 6. 归一化 + Neo4j 导出/入库 | 100% | 已完成并验证通过（基于 7568 条成功抽取） |
| 6.1 图谱质量标注 + 保守实体合并 | 100% | 已完成 v2 小批量 curated 归并并重新入库 |
| 7. Embedding + 向量库 | 100% | 已完成 |
| 8. 混合检索原型 | 100% | 已验证通过 |
| 9. KGRAG 问答原型 | 90% | CLI + HTTP API + 批量评估基线已完成，dry-run 10/10、小样本真实生成 4/4 通过 |

全链路打通进度：**约 98%**（离线建库、图谱质量 v2 处理、混合检索、KGRAG CLI/API 问答生成和基础评估闭环已完成）

一句话判断：

`离线建库管线已完整打通（提取→清洗→分块→抽取→归一化→Neo4j+Qdrant入库→混合检索验证）；实体关系抽取已完成全量抽取和两轮失败重试，成功覆盖率达到 100%。当前图谱已完成质量标注、保守实体合并、v2 小批量 curated 归并和 Neo4j 重新入库，KGRAG CLI/API 问答原型已完成基础评估闭环。`

---

## 各阶段详情

### 1. 数据提取 100%

- 输入：`data/raw/`
- 输出：`data/processed/extract_raw_full`
- 文档总数：456，全部成功

### 2. 数据清洗 100%

- 输出：`data/processed/cleaned_full`
- A/B 可保留：441 篇，C/D 复核：15 篇

### 3. 分块 100%

- 输出：`data/processed/chunks_full`
- chunk 总数：17797
- 高价值主干输入：`data/processed/chunks_extractable_full_ab_nonbook.jsonl`，7568 条

### 4. 元数据补全 100%

- 输出：`data/processed/source_catalog/`
- 每篇文档含 title/year/source_type/evidence_level/include_flag/license

### 5. 实体关系抽取 100%

- 第一轮全量抽取：7568 / 7568 已尝试，3040 成功，4528 失败
- 第一轮 transient 失败重试：4521 条已尝试，4408 成功，113 失败
- 第二轮剩余失败重试：115 条已尝试，115 成功，0 失败
- 当前合并/重校验基线：7568 成功，0 失败，成功覆盖率 100%
- 当前策略：冻结 extraction v5 current 作为图谱构建基线，进入 Neo4j 入库验证和 KGRAG 问答原型

已完成的工具链：

- 抽取脚本：`scripts/extraction/extract_entities_relations.py`
  - 支持 stub / openai backend
  - 支持 resume 断点续跑
  - 支持 max_tokens / response_format / 轻量 prompt
  - socket timeout / SSL / 连接异常 retry 覆盖
  - 宽松 JSON 解析（处理模型返回代码块或前后说明文本）
- 批处理脚本：
  - `run_next_extraction_batch.sh`（throughput/balanced 双模式）
  - `run_full_extraction_batches.sh`
  - `rerun_timeouts_and_merge.sh`
  - `refresh_current_outputs.sh`
  - `run_extraction_until_complete.sh`（后台持续抽取，带运行锁，支持断点续抽）
  - `run_retry_until_complete.sh`（后台持续重试 transient 失败项，带运行锁，完成后自动刷新 current outputs）
- 后处理脚本：
  - `merge_extraction_runs.py`
  - `revalidate_extraction_run.py`
  - `normalize_extractions.py`
  - `summarize_extraction_run.py`
- Prompt：
  - v5 原版：`entity_relation_system_prompt.txt`
  - v6 轻量版：`entity_relation_system_prompt_v6_light.txt`（吞吐模式默认使用）

模型调用配置入口：

```bash
export LLM_BASE_URL="https://api.siliconflow.cn/v1/chat/completions"
export LLM_API_KEY="你的_key"
export LLM_MODEL="deepseek-ai/DeepSeek-V4-Flash"
export LLM_MAX_TOKENS=1200
export LLM_RESPONSE_FORMAT=json_object
```

继续推进命令：

```bash
nohup scripts/extraction/run_extraction_until_complete.sh >/tmp/asd_kgrag_extract_daemon.out 2>&1 &
```

### 6. 归一化 + Neo4j 导出/入库 100%

- 归一化脚本：`scripts/extraction/normalize_extractions.py`
- Neo4j 导出：`scripts/graph/export_neo4j_import.py`
- Cypher loader 生成：`scripts/graph/generate_neo4j_load_cypher.py`
- 验证查询：`scripts/graph/write_validation_queries.py`

当前 normalized 规模（基于 7568 条成功抽取）：

- Entity：3706
- Evidence：7568
- Chunk：7568
- INDICATED_FOR：537
- MEASURED_BY：257
- COMORBID_WITH：83
- SUITABLE_AGE：43
- HAS_RISK：32
- SUITABLE_SETTING：27
- NOT_INDICATED_FOR：8

Neo4j 连接：bolt://localhost:7687，neo4j / asd-kgrag-local

### 6.1 Neo4j 入库验证 100%

验证时间：2026-06-08

验证方式：

- 启动本地 `docker compose` 服务
- 清空 Neo4j 本地图数据库，避免旧数据影响验证
- 执行 `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher`
- 执行 `validation_queries.cypher` 和额外计数查询
- 执行 `scripts/retrieval/hybrid_search.py` smoke test，确认 Neo4j + Qdrant 混合检索仍可用

Neo4j 实际入库计数：

- Chunk：7568
- Entity：3706
- Evidence：7568
- FROM：7568
- FROM_CHUNK：7568
- SUPPORTED_BY：1704
- INDICATED_FOR：537
- MEASURED_BY：257
- COMORBID_WITH：83
- SUITABLE_AGE：43
- HAS_RISK：32
- SUITABLE_SETTING：27
- NOT_INDICATED_FOR：8

混合检索 smoke test：

- 查询：`ADOS autism diagnostic observation schedule`
- 图检索：20 entities，42 relations，300 chunks
- 向量检索：5 hits
- top-5 中出现 `G+V` 双重命中结果，说明 Neo4j 图召回和 Qdrant 向量召回链路均可用

### 6.2 图谱质量标注 + 保守实体合并 100%

处理时间：2026-06-08

目标：

- 不直接粗暴删除实体，先在 normalized 和 Neo4j 层写入可审计质量字段
- 仅合并高置信的同类型同名实体，避免误伤年龄、场景、机制、任务等语义边界敏感实体
- 为后续 KGRAG 问答提供 `qa_usage` 和 `tool_category` 护栏字段

当前保守合并范围：

- 允许合并：`AssessmentTool`、`Intervention`、`Condition`、`Symptom`、`Comorbidity`、`Risk`
- 暂不合并：`AgeStage`、`Setting`、`Mechanism`、`Task`

首轮保守合并结果：

- Entity：3706 → 3688，减少 18 个
- Relation：987 → 980，减少 7 条重复/自环关系
- Merge group：18 组
- 已确认示例：M-CHAT、SRS、AQ-Adult、音乐治疗、感觉统合训练、催产素、睡眠问题、破坏性行为、情绪识别障碍

质量标注后图谱概览：

- Entity：3688
- Evidence：7568
- Chunk：7568
- Entity relations：980
- SUPPORTS：1702
- FROM：7568

质量问题剩余量：

- 孤立实体：2800
- 同名重复组：121
- 别名跨类型冲突实体：414
- 单 chunk 实体：2514

关系回答策略分布：

- `guardrailed_clinical_context`：574
- `use_with_caution`：329
- `research_context_only`：43
- `standard`：34

当前判断：

首轮质量处理已经完成“可审计标注 + 低风险归并”，图谱可以作为 KGRAG 原型基线。剩余的同名重复和别名冲突数量仍高，不应继续用全自动粗规则处理。

### 6.3 高价值 curated alias 归并 v2 100%

处理时间：2026-06-08

新增配置：

- `config/graph/curated_entity_alias_map.json`

策略：

- 只使用显式 alias map
- 只合并同类型实体
- 不合并跨类型冲突实体
- 暂不扩大 ADOS / ADI-R / M-CHAT-R/F 等版本边界复杂的工具归并

v2 归并结果：

- Entity：3706 → 3684，累计减少 22 个
- Relation：987 → 978，累计减少 9 条重复/自环关系
- Merge group：21 组
- 其中同类型同名合并：18 组
- curated alias map 合并：3 组

新增 curated 合并组：

- `AssessmentTool`：ATEC / 自闭症治疗评估量表（ATEC）
- `AssessmentTool`：CARS / CARS-2 / Childhood Autism Rating Scale: Second edition
- `Intervention`：应用行为分析 / ABA训练法

v2 当前 Neo4j 图谱概览：

- Entity：3684
- Evidence：7568
- Chunk：7568
- Entity relations：978
- SUPPORTS：1702
- FROM：7568
- `MEASURED_BY`：251
- `INDICATED_FOR`：534

v2 smoke test：

- 查询：`ADOS autism diagnostic observation schedule`
- 图检索：20 entities，41 relations，310 chunks
- 向量检索：5 hits
- top-5 仍有 `G+V` 双重命中，Neo4j + Qdrant 混合检索链路正常

### 7. Embedding + 向量库 100%

- 模型：BAAI/bge-small-zh-v1.5（512 维，CPU 可跑，中文优化）
- 向量库：Qdrant，localhost:6333
- Collection：asd_kgrag_chunks，7568 条向量已写入
- 脚本：
  - `scripts/embedding/embed_chunks.py`
  - `scripts/embedding/search_chunks.py`
- 设计文档：`scripts/embedding/README.md`

已从 all-MiniLM-L6-v2 升级到 bge-small-zh-v1.5，中文查询 score 从 0.46 提升到 0.77，混合检索双重命中率显著改善。

### 8. 混合检索原型 100%

- 脚本：`scripts/retrieval/hybrid_search.py`
- 架构：
  - 图检索（Neo4j）：关键词匹配 Entity → 1-hop 子图扩展 → 关联 Chunk
  - 向量检索（Qdrant）：query embedding → cosine top-K
  - 合并：双重命中 +0.15 boost + 证据等级加权
  - 自动中文关键词拆分（正则提取英文词和中文词组）
- 验证结果：
  - 英文查询（如 "ADOS autism diagnostic observation schedule"）：top-8 全部 [G+V] 双重命中，score 0.7-0.8
  - 中文查询受 embedding 模型限制，双重命中率偏低
  - 纯向量查询 score 0.4-0.6，混合后提升至 0.7-0.8

### 9. KGRAG 问答原型 90%

- CLI 入口：`scripts/qa/kgrag_answer.py`
- HTTP API 入口：`scripts/qa/kgrag_api.py`
- 使用文档：`scripts/qa/README.md`
- 当前能力：
  - 自动读取 `.env` 中的 LLM 配置
  - Neo4j 图实体/关系召回
  - Qdrant 向量召回
  - 图关系证据 chunk 优先注入问答上下文
  - 基于 curated alias map 的查询侧别名扩展，例如 `ABA` 可召回“应用行为分析”
  - 具体实体词优先，例如 ADOS 优先于 ASD/孤独症这类泛词
  - 证据片段围绕关键词截取，避免 chunk 前半段噪声遮挡关键证据
  - prompt 内置文献引用 `[C1]`、图谱关系引用 `[G1]` 和诊断/干预/用药/风险护栏
  - 支持 `--dry-run` 验证检索、上下文和 prompt，不调用 LLM
  - 标准库 HTTP API：`GET /health`、`POST /ask`
  - 批量评估脚本：`scripts/qa/evaluate_qa.py`
  - 评估题集：`scripts/qa/eval_questions.jsonl`

已验证 dry-run：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --dry-run \
  --context-k 6 \
  --graph-evidence-k 4
```

验证结果：

- 图检索：20 entities，50 relations，487 chunks
- 上下文：6 条
- ADOS 相关关系被优先召回：
  - `孤独症 -MEASURED_BY-> ADOS`
  - `孤独症 -MEASURED_BY-> ADOS-2`
  - `PDDs -MEASURED_BY-> ADOS`
- 证据片段已围绕 `ADOS` 关键词截取

已验证真实 LLM 生成：

```bash
.venv/bin/python scripts/qa/kgrag_answer.py \
  "ADOS 是什么? 它在 ASD 评估中有什么作用?" \
  --context-k 4 \
  --graph-evidence-k 2
```

验证结果：

- LLM 成功生成中文结构化回答
- 文献证据引用格式：`[C1]`、`[C2]`
- 图谱关系引用格式：`[G2]`、`[G3]`
- 回答包含证据边界和“不能替代专业评估或临床决策”的护栏

已验证 HTTP API：

```bash
.venv/bin/python scripts/qa/kgrag_api.py --host 127.0.0.1 --port 8010
```

```bash
curl -sS http://127.0.0.1:8010/health

curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true,"context_k":4,"graph_evidence_k":2}'
```

验证结果：

- `/health` 返回 `{"status":"ok","service":"kgrag-qa"}`
- `/ask` dry-run 返回 query、contexts、relations 和 prompt preview
- `/ask` 真实生成返回 answer、contexts、relations 的结构化 JSON

已完成批量评估基线：

```bash
.venv/bin/python scripts/qa/evaluate_qa.py --dry-run --context-k 6 --graph-evidence-k 4
```

dry-run 结果：

- 题数：10
- 通过：10/10
- 平均上下文数：6.0
- 平均图关系数：10.9
- 上下文引用覆盖率：100%
- 图关系召回覆盖率：100%
- 期望实体词命中率：100%（9/9，安全泛问题不计入）

```bash
.venv/bin/python scripts/qa/evaluate_qa.py \
  --ids assessment_ados intervention_aba comorbidity_sleep safety_direct_treatment \
  --context-k 4 \
  --graph-evidence-k 2
```

真实生成小样本结果：

- 题数：4
- 通过：4/4
- 回答引用覆盖率：100%
- 文献引用覆盖率：100%
- 图关系引用覆盖率：100%
- 临床护栏覆盖率：100%
- 输出目录：`data/qa_eval/20260608_164615_real`

本轮修正：

- 暴露问题：`ABA` 查询只能通过向量召回，图关系未命中。
- 原因：Neo4j 当前实体名是“应用行为分析”，查询侧未扩展英文缩写。
- 修正：QA 检索前读取 `config/graph/curated_entity_alias_map.json` 做受控别名扩展，并将“应用行为分析”补入 ABA curated alias group。

---

## 2026-06-03 至 2026-06-04 抽取推进记录

- 新增 `.env` 自动读取，`.env` 已加入 `.gitignore`，避免 API key 入库
- 新增 `--workers` 并发抽取能力，吞吐模式默认 `WORKERS=3`
- 先跑 3 条探针：1 成功、2 错误，确认接口可用但慢
- 再跑 10 条并发批次：6 成功、4 错误
- 再跑 30 条并发批次：19 成功、11 错误
- 2026-06-04 继续推进后，当前合并/重校验后基线：1305 行，975 成功，330 错误
- 已刷新 normalized、Neo4j import、summary report
- 最新导出：Chunk 7568，Evidence 975，Entity 1790，实体关系 376

## 2026-06-05 至 2026-06-07 抽取推进记录

- 第一轮全量抽取已完成：7568 / 7568 全部尝试
- 第一轮全量结果：3040 成功，4528 失败，主要失败来自 SSL EOF、证书校验失败、timeout、DNS 临时解析失败
- 新增 `scripts/extraction/run_retry_until_complete.sh`，支持失败项后台断点重试
- 第一轮 transient retry 输入：4521 条
- 第一轮 transient retry 结果：4408 成功，113 失败
- 当前合并/重校验结果：7453 成功，115 失败，成功覆盖率 98.48%
- 当前剩余失败：SSL EOF 107 条，空/异常 API 响应 5 条，模型 JSON 解析错误 2 条，timeout 1 条
- 下一步：生成 115 条 remaining retry 输入，单独写入第二轮 retry 输出目录，避免覆盖第一轮 retry 结果
- 第二轮 remaining retry 已完成：115 条全部成功
- 最终合并/重校验结果：7568 成功，0 失败，成功覆盖率 100%
- 最新 normalized：Entity 3706，Evidence 7568，实体关系 987
- 最新 Neo4j import：Entity 3706，Evidence 7568，Chunk 55435，实体关系 992，SUPPORTS 1704，FROM 7568

## 后台持续抽取方案

已新增 `scripts/extraction/run_extraction_until_complete.sh`。这是当前抽取推进主入口，目标是一次性挂后台跑完整个剩余抽取任务。该脚本会：

- 自动读取 `.env`
- 循环调用 `run_next_extraction_batch.sh`
- 依赖 `resume + start_index` 断点续抽，已经写入 `chunk_extractions.jsonl` 的 chunk 不会重复抽取
- 使用运行锁 `data/logs/extraction/run_until_complete.lock`，避免误启动多个守护进程并发写同一个输出文件
- 默认参数：`MODE=throughput BATCH_SIZE=30 WORKERS=3 REQUEST_TIMEOUT=90 MAX_RETRIES=0`
- 每 `REFRESH_EVERY_BATCHES=10` 批自动刷新 current outputs
- 日志写入 `data/logs/extraction/run_until_complete_*.log`
- 所有 `7568` 条 chunk 都被尝试后自动最终 refresh 并退出

启动命令：

```bash
nohup scripts/extraction/run_extraction_until_complete.sh >/tmp/asd_kgrag_extract_daemon.out 2>&1 &
```

查看状态：

```bash
pgrep -fa run_extraction_until_complete
tail -f data/logs/extraction/run_until_complete_*.log
```

## 当前问题与卡点

1. **QA 评估规模仍小**：当前只有 10 个 dry-run 种子问题和 4 个真实生成样本，足够做 smoke/e2e baseline，但还不能代表稳定产品质量。
2. **批量评估性能偏慢**：当前每题会重新初始化 embedding 模型，dry-run 10 题约 2 分钟；后续应把模型、Qdrant client、Neo4j driver 提升为批处理级缓存。
3. **API 服务壳仍是原型**：当前使用标准库 HTTP server，适合本地验证；如果要长期运行或接前端，应迁移到 FastAPI/uvicorn 或容器化服务入口。
4. **图谱仍有 curated 质量空间**：v2 alias 已处理 ATEC/CARS/ABA，但 ADOS/ADI-R/M-CHAT-R/F 等版本边界复杂实体仍需人工抽样后再决定是否归并。

---

## 推进计划表

### 近期（1-2 天内）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| R1 | 合并 docker-compose 为单文件，清理旧文件 | 已完成 | - |
| R2 | 升级 embedding 模型到 bge-small-zh-v1.5，重跑 7568 条嵌入 | 已完成 | - |
| R3 | 启动后台守护抽取，直到 7568 条全部尝试完成 | 已完成 | - |
| R4 | 第一轮失败项 transient retry | 已完成 | - |
| R5 | 第二轮重试剩余 115 条失败样本 | 已完成 | - |
| R6 | 第二轮重试完成后统一 refresh normalized / Neo4j import / summary report | 已完成 | - |
| R6b | 执行 Neo4j 入库验证 | 已完成 | - |
| R7 | 图谱质量首轮处理：质量标注 + 保守实体合并 + Neo4j 重新入库 | 已完成 | - |
| R8 | 高价值 curated alias 归并 v2：ATEC/CARS/ABA + Neo4j 重新入库 | 已完成 | - |
| R9 | 建立 QA 评估题集和批量评估脚本 | 已完成 | - |

### 中期（3-5 天内）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| M1 | KGRAG CLI 问答原型：检索上下文 + prompt + LLM 生成 | 已完成 | - |
| M2 | KGRAG API 服务化：HTTP API `/ask` + `/health` | 已完成 | - |
| M2a | 优化 QA 批评估性能：缓存 embedding model / Qdrant client / Neo4j driver | 高 | 1h |
| M2b | 可选替换为 FastAPI/uvicorn 服务壳或容器化 API 服务 | 中 | 1h |
| M2c | 扩展 QA 评估题集到 30-50 题，覆盖评估工具、干预、共病、风险、安全拒答 | 高 | 2h |
| M3 | Entity card embedding：生成实体卡片文本 + 嵌入 + Qdrant entity collection | 中 | 2h |
| M4 | 继续小批量 curated alias 归并，必须基于人工抽样确认 | 中 | 持续 |
| M5 | 冻结 extraction v5 current 作为图谱构建基线 | 已完成 | - |

### 远期（1-2 周）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| L1 | Query 路由：自动分流到知识问答 / 干预建议两种模式 | 中 | 3h |
| L2 | 评测框架：纯 LLM vs 纯 RAG vs KGRAG 对比 + 可追溯性指标 | 高 | 4h |
| L3 | 社区摘要 embedding（需要图社区检测算法） | 低 | 3h |
| L4 | 扩展人工评测与对比实验，形成可复现 QA 质量报告 | 中 | 持续 |
| L5 | 前端界面 / Web Demo | 低 | 视需求 |

---

## 基础设施

Docker 服务（一键启动：`docker compose up -d`）：

| 服务 | 端口 | 用途 |
|------|------|------|
| Neo4j | 7474 (HTTP), 7687 (Bolt) | 图谱存储与子图召回 |
| Qdrant | 6333 (gRPC), 6334 (REST) | 向量存储与语义搜索 |

认证：
- Neo4j: neo4j / asd-kgrag-local
- Qdrant: 无认证（本地开发）

Python 依赖（.venv）：
- sentence-transformers 5.5.1
- qdrant-client 1.18.0
- torch 2.12.0+cu130 (CPU mode)
- neo4j 6.2.0

---

## 当前结论

离线建库管线已完整打通（提取→清洗→分块→抽取→归一化→Neo4j+Qdrant入库→混合检索验证），当前全链路进度约 98%。实体关系抽取成功覆盖率 100%，Neo4j 已完成质量标注、保守实体合并、v2 curated alias 归并和重新入库。KGRAG CLI/API 问答原型已完成基础评估闭环，下一步应优先优化 QA 批评估性能并扩展评估题集，再推进 API 服务化和前端体验。
