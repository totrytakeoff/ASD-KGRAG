# 项目状态记录

更新时间：2026-06-07

## 总体进度

| 阶段 | 进度 | 状态 |
|------|------|------|
| 1. 数据提取 | 100% | 已完成 |
| 2. 数据清洗 | 100% | 已完成 |
| 3. 分块 | 100% | 已完成 |
| 4. 元数据补全 | 100% | 已完成 |
| 5. 实体关系抽取 | 100% | 全量抽取 + 两轮失败重试已完成（7568/7568 成功，0 失败） |
| 6. 归一化 + Neo4j 导出/入库 | 100% | 已完成（基于 7568 条成功抽取；待执行 Neo4j 入库验证） |
| 7. Embedding + 向量库 | 100% | 已完成 |
| 8. 混合检索原型 | 100% | 已验证通过 |
| 9. KGRAG 问答原型 | 0% | 未开始 |

全链路打通进度：**约 65%**（离线管线已完整跑通，在线问答待搭建）

一句话判断：

`离线建库管线已完整打通（提取→清洗→分块→抽取→归一化→Neo4j+Qdrant入库→混合检索验证）；实体关系抽取已完成全量抽取和两轮失败重试，成功覆盖率达到 100%。当前主要剩余工作是执行 Neo4j 入库验证，并搭建 KGRAG 在线问答原型。`

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

### 9. KGRAG 问答原型 0%

待搭建。详见下方推进计划。

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

1. **LLM 抽取吞吐低**：SiliconFlow 接口在真实抽取任务上延迟高（35-90s），成功率和吞吐量低
   - 已排查确认：URL/key/model 配置正确，简单请求 7/7 成功
   - 轻量 prompt + max_tokens 限流有改善但不能完全抵消
   - 当前处理：不再人工轮询批次，改为后台守护脚本持续推进；默认 `WORKERS=3`，暂不提升到 5，避免 DNS/连接错误显著增加
2. **中文 embedding 已升级到 bge-small-zh-v1.5**：中文查询 score 从 0.46 提升到 0.77
3. **抽取覆盖率低**：当前约 12.88% 的 chunk 有成功抽取结果，图谱规模受限于抽取进度
   - 不影响管线搭建，但会影响最终问答质量

---

## 推进计划表

### 近期（1-2 天内）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| R1 | 合并 docker-compose 为单文件，清理旧文件 | 已完成 | - |
| R2 | 升级 embedding 模型到 bge-small-zh-v1.5，重跑 7568 条嵌入 | 高 | 30min |
| R3 | 启动后台守护抽取，直到 7568 条全部尝试完成 | 已完成 | - |
| R4 | 第一轮失败项 transient retry | 已完成 | - |
| R5 | 第二轮重试剩余 115 条失败样本 | 已完成 | - |
| R6 | 第二轮重试完成后统一 refresh normalized / Neo4j import / summary report | 已完成 | - |
| R6b | 执行 Neo4j 入库验证 | 高 | 10min |
| R7 | 完善 hybrid_search：增加 graph-only fallback、增加 top-k 到向量结果里也返回 chunk text | 中 | 1h |

### 中期（3-5 天内）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| M1 | 搭建 KGRAG 问答原型：FastAPI + hybrid_search + LLM 生成 | 高 | 4h |
| M2 | 问答 prompt 设计：结构化回答模板 + 安全护栏 + 引用格式 | 高 | 2h |
| M3 | Entity card embedding：生成实体卡片文本 + 嵌入 + Qdrant entity collection | 中 | 2h |
| M4 | 冻结 extraction v5 current 作为图谱构建基线 | 已完成 | - |

### 远期（1-2 周）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| L1 | Query 路由：自动分流到知识问答 / 干预建议两种模式 | 中 | 3h |
| L2 | 评测框架：纯 LLM vs 纯 RAG vs KGRAG 对比 + 可追溯性指标 | 高 | 4h |
| L3 | 社区摘要 embedding（需要图社区检测算法） | 低 | 3h |
| L4 | 抽取覆盖 50%+ 并重刷整条管线 | 中 | 持续 |
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

离线建库管线已完整打通（提取→清洗→分块→抽取→归一化→Neo4j+Qdrant入库→混合检索验证），当前全链路进度约 85%。实体关系抽取已完成全量抽取和两轮失败重试，成功覆盖率 100%。下一步先执行 Neo4j 入库验证，再进入 KGRAG 问答原型。
