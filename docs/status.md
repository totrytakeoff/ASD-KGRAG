# 项目状态记录

更新时间：2026-06-03

## 总体进度

| 阶段 | 进度 | 状态 |
|------|------|------|
| 1. 数据提取 | 100% | 已完成 |
| 2. 数据清洗 | 100% | 已完成 |
| 3. 分块 | 100% | 已完成 |
| 4. 元数据补全 | 100% | 已完成 |
| 5. 实体关系抽取 | 8% | 进行中（815/7568 已尝试，接口超时为主要卡点） |
| 6. 归一化 + Neo4j 导出/入库 | 100% | 已完成（基于已抽取部分） |
| 7. Embedding + 向量库 | 100% | 已完成 |
| 8. 混合检索原型 | 100% | 已验证通过 |
| 9. KGRAG 问答原型 | 0% | 未开始 |

全链路打通进度：**约 65%**（离线管线已完整跑通，在线问答待搭建）

一句话判断：

`离线建库管线已完整打通（提取→清洗→分块→抽取→归一化→Neo4j+Qdran入库→混合检索验证）；当前主要卡点是 LLM 抽取接口慢导致覆盖率偏低（8%），以及 KGRAG 在线问答原型尚未搭建。`

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

### 5. 实体关系抽取 8%

- 已尝试：815 / 7568 = 10.8%
- 成功：616 条
- 失败：199 条（主要是接口超时）
- 剩余未尝试：6753 条

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
- 后处理脚本：
  - `merge_extraction_runs.py`
  - `revalidate_extraction_run.py`
  - `normalize_extractions.py`
  - `summarize_extraction_run.py`
- Prompt：
  - v5 原版：`entity_relation_system_prompt.txt`
  - v6 轻量版：`entity_relation_system_prompt_v6_light.txt`（吞吐模式默认使用）

模型调用配置入口：



继续推进命令：



### 6. 归一化 + Neo4j 导出/入库 100%

- 归一化脚本：`scripts/extraction/normalize_extractions.py`
- Neo4j 导出：`scripts/graph/export_neo4j_import.py`
- Cypher loader 生成：`scripts/graph/generate_neo4j_load_cypher.py`
- 验证查询：`scripts/graph/write_validation_queries.py`

当前图谱规模（基于 616 条成功抽取）：

- Entity：1707
- Evidence：616
- Chunk：7568
- MEASURED_BY：146
- INDICATED_FOR：138
- COMORBID_WITH：31
- SUITABLE_AGE：20
- SUITABLE_SETTING：6
- HAS_RISK：6
- NOT_INDICATED_FOR：3

Neo4j 连接：bolt://localhost:7687，neo4j / asd-kgrag-local

### 7. Embedding + 向量库 100%

- 模型：all-MiniLM-L6-v2（384 维，CPU 可跑）
- 向量库：Qdrant，localhost:6333
- Collection：asd_kgrag_chunks，7568 条向量已写入
- 脚本：
  - `scripts/embedding/embed_chunks.py`
  - `scripts/embedding/search_chunks.py`
- 设计文档：`scripts/embedding/README.md`

已知限制：all-MiniLM-L6-v2 以英文为主，中文查询相似度偏低；后续可升级到 bge-small-zh-v1.5。

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

## 当前问题与卡点

1. **LLM 抽取吞吐低**：SiliconFlow 接口在真实抽取任务上延迟高（35-90s），成功率和吞吐量低
   - 已排查确认：URL/key/model 配置正确，简单请求 7/7 成功
   - 轻量 prompt + max_tokens 限流有改善但不能完全抵消
   - 建议：接口窗口好时小批次推进，或换更快的模型/接口
2. **中文 embedding 效果偏弱**：all-MiniLM-L6-v2 中文语义捕捉能力有限
   - 升级到 bge-small-zh-v1.5 可显著改善
3. **抽取覆盖率低**：仅 8% 的 chunk 被抽取，图谱规模受限于抽取进度
   - 不影响管线搭建，但会影响最终问答质量

---

## 推进计划表

### 近期（1-2 天内）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| R1 | 合并 docker-compose 为单文件，清理旧文件 | 已完成 | - |
| R2 | 升级 embedding 模型到 bge-small-zh-v1.5，重跑 7568 条嵌入 | 高 | 30min |
| R3 | 接口可用时继续 LLM 抽取（MODE=throughput 小批次） | 中 | 持续 |
| R4 | 完善 hybrid_search：增加 graph-only fallback、增加 top-k 到向量结果里也返回 chunk text | 中 | 1h |

### 中期（3-5 天内）

| # | 任务 | 优先级 | 预估工时 |
|---|------|--------|----------|
| M1 | 搭建 KGRAG 问答原型：FastAPI + hybrid_search + LLM 生成 | 高 | 4h |
| M2 | 问答 prompt 设计：结构化回答模板 + 安全护栏 + 引用格式 | 高 | 2h |
| M3 | Entity card embedding：生成实体卡片文本 + 嵌入 + Qdrant entity collection | 中 | 2h |
| M4 | 抽取进度推进到 30%+（约 2270 条成功） | 中 | 取决于接口 |

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

离线建库管线已完整打通（提取→清洗→分块→抽取→归一化→Neo4j+Qdran入库→混合检索验证），当前全链路进度约 65%。两大缺口是：(1) LLM 抽取覆盖率只有 8%，受限于接口延迟；(2) KGRAG 在线问答原型尚未搭建。下一步优先升级中文 embedding 模型和搭建问答原型，同时继续推进抽取覆盖率。
