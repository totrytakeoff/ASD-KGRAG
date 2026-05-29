# 项目状态记录

更新时间：2026-05-29

## 当前阶段

当前项目处于：

`主干高价值语料批量实体关系抽取执行中，已跑通归一化与 Neo4j 导出闭环`

更具体地说：

1. 原始文档提取已完成
2. 清洗与质量评估已完成
3. 分块与 chunk 质量评估已完成
4. 文档级元数据补全已完成
5. 实体关系抽取 schema、prompt、脚本和 OpenAI-compatible backend 已完成
6. 多轮真实 pilot 已完成，关系抽取规则已基本成型
7. 高价值主干语料已开始批量抽取
8. 抽取结果已部分跑通归一化与 Neo4j CSV 导出
9. embedding、向量库和在线 KGRAG 查询链路尚未开始

一句话判断：

`项目已从 pilot 质量收敛阶段，进入“7568 条主干 chunk 的批量抽取、错误重跑、合并、归一化和导图”阶段。`

由于当前模型接口窗口 timeout/SSL 错误偏多，已并行推进不依赖 LLM 的 Neo4j 实入库准备与本地验证；本地 Neo4j 入库已跑通，当前主卡点集中在真实 LLM 抽取吞吐。

## 已完成工作

### 1. 数据提取

- 输入语料已整理到 `data/raw/`
- 提取结果位于 `data/processed/extract_raw_full`
- 文档总数：`456`
- 提取成功：`456`
- 失败：`0`

相关文件：

- `docs/data_process/extraction_summary.md`
- `scripts/extraction/extract_raw_corpus.py`

### 2. 数据清洗

- 清洗结果位于 `data/processed/cleaned_full`
- 清洗质量门禁已通过
- `A/B` 可保留文档：`441`
- `C/D` 复核文档：`15`

相关文件：

- `scripts/cleaning/clean_extracted_corpus.py`
- `scripts/cleaning/assess_clean_quality.py`

### 3. Chunk 构建

- 分块结果位于 `data/processed/chunks_full`
- chunk 总数：`17797`
- 可用于 KGRAG 的 chunk 已生成
- 已附加 `title/year/source_type/evidence_level/include_flag/language`

主干抽取输入：

- `data/processed/chunks_extractable_full_ab_nonbook.jsonl`
- chunk 数：`7568`
- 过滤策略：`A/B` 证据等级、非书籍、去噪 chunk

相关文件：

- `scripts/chunking/build_context_chunks.py`
- `scripts/chunking/assess_chunk_quality.py`
- `docs/data_process/source_metadata_sop.md`

### 4. 文档元数据目录

- 已新增 `source_catalog`
- 生成文档级元数据：
  - `title`
  - `year`
  - `source_type`
  - `evidence_level`
  - `include_flag`
  - `license`

相关文件：

- `scripts/metadata/build_source_catalog.py`
- `data/processed/source_catalog/source_metadata.jsonl`
- `data/processed/source_catalog/source_metadata.csv`

### 5. 实体关系抽取

已完成：

- 抽取 schema：`scripts/extraction/entity_relation_schema.json`
- 抽取 prompt：`scripts/extraction/entity_relation_system_prompt.txt`
- 抽取脚本：`scripts/extraction/extract_entities_relations.py`
- 支持 `stub` 模式和 OpenAI-compatible backend
- 支持环境变量：
  - `LLM_BASE_URL`
  - `LLM_API_KEY`
  - `LLM_MODEL`
  - `LLM_MAX_TOKENS`
  - `LLM_RESPONSE_FORMAT`
- 已加入：
  - 类型纠偏
  - 关系合法性校验
  - 弱证据过滤
  - 请求重试与退避
  - socket timeout / SSL EOF / HTTP 连接异常重试覆盖
  - OpenAI-compatible `response_format` 可关闭入口
  - 输出 `max_tokens` 可配置入口
  - 每条结果即时落盘
  - `resume` 断点续跑
  - `start-index` 分段切片运行
  - 超时重跑输入构建
  - 多轮抽取结果按 `chunk_id` 合并

已完成的关键 pilot：

- `rich3`：`3/3` 成功，归一化与 Neo4j 导出已跑通
- `curated6 v2-v4`：完成保守召回、任务/工具混淆修正和 precision 收敛
- `curated12 v4/v5`：完成研究模态工具门槛验证，Neo4j 导出通过
- `curated100 v5`：完成 100 条级别回归，证明规则可进入主干批量运行

当前主干抽取产物：

- 主抽取目录：`data/processed/extraction_full_ab_nonbook_v5`
- retry 目录：`data/processed/extraction_full_ab_nonbook_v5_retry`
- 当前正式合并文件：`data/processed/extraction_full_ab_nonbook_v5_merged.jsonl`
- 重校验合并文件：`data/processed/extraction_full_ab_nonbook_v5_merged_revalidated.jsonl`
- 当前质量报告：`data/processed/extraction_full_ab_nonbook_v5_current_revalidated_report`

截至本记录更新时，按主抽取 + retry 重新合并后的实际进度为：

- 主干输入总数：`7568`
- 已尝试唯一 chunk：`815`
- 成功：`616`
- 失败：`199`
- 剩余未尝试：`6753`
- 已尝试成功率：约 `75.6%`
- 原始实体数：`4406`
- 重校验后原始关系数：`527`
- 重校验后平均每个成功 chunk：约 `0.85` 条关系

注意：

- `data/processed/extraction_full_ab_nonbook_v5_merged.jsonl` 已从较早的 `371` 行版本更新到 `815` 行
- `data/processed/extraction_full_ab_nonbook_v5_merged_revalidated.jsonl` 已用当前校验规则离线重校验，不需要重新调用模型
- 最近一轮 25 条小批次受接口影响较大，新增结果中 timeout/SSL 错误偏多
- 已对 timeout 队列做一轮小批次 retry，回收效果有限：`11` 条 retry 中 `6` 条成功、`5` 条仍错误；纳入合并后总成功数净增 `1`
- 为平衡质量与效率，已新增吞吐模式：`MODE=throughput bash scripts/extraction/run_next_extraction_batch.sh`
- 吞吐模式现默认使用轻量 prompt：`scripts/extraction/entity_relation_system_prompt_v6_light.txt`
- 吞吐模式现默认传入 `MAX_TOKENS=1200`，可通过环境变量覆盖
- 最近两轮吞吐模式分别覆盖 `24` 条和 `16` 条；后一轮 `7` 条成功、`9` 条错误。当前接口状态偏慢，吞吐模式仍适合避免停滞，但成功率会下降
- 最近一轮吞吐模式继续尝试 `10` 条后人工停止，`10` 条均为 timeout/connection 错误；当前接口窗口不适合继续硬跑模型请求
- 2026-05-29 轻量 prompt 探针：3 条真实中等 chunk 中 `1` 条成功、`2` 条 timeout；随后单条 `35-45s` 探针仍 timeout，说明 API/key/url/model 可用但当前真实抽取延迟窗口仍偏差
- 已清理可再生/过期中间产物：非重校验 `current` 图谱导出、`partial372` 归一化和 Neo4j 导出、Python `__pycache__`
- 已建立 git 基线提交：`1476018`，并提交 `run_next_extraction_batch.sh` 可执行权限修正：`d1f2661`

### 6. 归一化与 Neo4j 导出

已实现：

- `scripts/extraction/normalize_extractions.py`
- `scripts/graph/export_neo4j_import.py`
- `scripts/graph/generate_neo4j_load_cypher.py`
- `scripts/graph/write_validation_queries.py`
- `docs/data_process/graph_export_sop.md`

已验证产物：

- `data/processed/normalized_full_ab_nonbook_v5_partial372`
- `data/processed/neo4j_import_full_ab_nonbook_v5_partial372`
- `data/processed/normalized_full_ab_nonbook_v5_current_revalidated`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/load_current.cypher`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/validation_queries.cypher`

`partial372` 归一化摘要：

- 输入行数：`371`
- 实体：`894`
- 聚合关系：`157`
- evidence：`275`

`partial372` Neo4j 导出摘要：

- entity nodes：`894`
- chunk nodes：`7568`
- evidence nodes：`275`
- entity relationships：`157`
- supports relationships：`221`
- from relationships：`275`

注意：

- `partial372` 是早期阶段性验证产物
- 当前推荐使用 `current_revalidated` 版本作为后续 Neo4j 导入和质量评估基线

`current_revalidated` 归一化摘要：

- 输入行数：`815`
- 实体：`1707`
- 聚合关系：`350`
- evidence：`616`
- 聚合关系分布：
  - `MEASURED_BY`: `146`
  - `INDICATED_FOR`: `138`
  - `COMORBID_WITH`: `31`
  - `SUITABLE_AGE`: `20`
  - `SUITABLE_SETTING`: `6`
  - `HAS_RISK`: `6`
  - `NOT_INDICATED_FOR`: `3`

`current_revalidated` Neo4j 导出摘要：

- entity nodes：`1707`
- chunk nodes：`7568`
- evidence nodes：`616`
- entity relationships：`350`
- supports relationships：`523`
- from relationships：`616`

Neo4j 实入库准备：

- 已生成 current 版 `LOAD CSV` Cypher loader
- 已生成基础验证查询：
  - 节点/关系计数
  - 实体类型分布
  - ASD/autism 相关筛查诊断工具
  - 干预适用目标
  - 关系证据回溯
  - 研究模态类 `MEASURED_BY` 人工复核查询
- loader 依赖 APOC 的 `apoc.merge.relationship` 来保留动态关系类型
- 已用 Docker Compose 启动本地 Neo4j 并完成 current 图谱入库验证
- 已修复归一化阶段少量重复 `entity_id` 输出问题，重刷 current 后 Neo4j 节点/关系计数与导出摘要一致
- 当前 Neo4j 验证计数：
  - `Chunk`: `7568`
  - `Entity`: `1707`
  - `Evidence`: `616`
  - `MEASURED_BY`: `146`
  - `INDICATED_FOR`: `138`
  - `COMORBID_WITH`: `31`

### 7. 新增质量工具与规则修正

本轮推进新增：

- `scripts/extraction/summarize_extraction_run.py`
  - 输出抽取批次摘要
  - 输出关系分布、证据等级分布、错误分布、高频 warning
  - 输出 `relation_samples.csv` 供人工抽样复核
- `scripts/extraction/revalidate_extraction_run.py`
  - 对已有抽取 JSONL 离线重套当前校验规则
  - 不重新调用模型
  - 用于规则修正后的快速重算
- `scripts/extraction/run_next_extraction_batch.sh`
  - 自动计算第一个未抽取 chunk 的 `start-index`
  - 以小批次继续推进主干抽取
  - 支持外层 timeout，避免慢接口拖住整轮执行
  - 支持 `MODE=balanced` 与 `MODE=throughput`
  - `MODE=throughput` 默认使用 v6 轻量 prompt 和 `MAX_TOKENS=1200`

本轮新增：

- `scripts/extraction/entity_relation_system_prompt_v6_light.txt`
  - 面向吞吐推进的轻量 prompt
  - 限制每 chunk 候选实体/关系数量
  - 强调只保留参与高置信关系的实体
  - 保留对研究模态、算法类工具、review-summary 弱证据的负向约束

本轮规则修正：

- 将 `机器学习`、`SVM/SVR`、`支持向量机`、`算法`、`分类器`、`模型` 等从 `AssessmentTool` 倾向中排除
- 对 `EEG/fMRI/sMRI/MRI` 等研究模态收紧 `MEASURED_BY` 保留条件
- 研究模态只有在证据中出现明确诊断性能信号时，才允许作为 `Condition -> MEASURED_BY -> AssessmentTool` 关系进入主图
- 保留 `ADOS`、`ADI-R`、`M-CHAT`、`CARS`、`ABC`、问卷、量表、访谈、观察表等临床筛查/诊断工具关系

## 当前问题与卡点

当前不是基础链路卡住，而是批量生产阶段的吞吐和稳定性问题：

1. 主干抽取已推进到 `815` 条尝试记录，当前 `merged -> revalidated -> normalized -> neo4j_import -> Neo4j load` 已同步到这一基线
2. 第三方模型接口仍有明显网络错误和长延迟，包括 timeout、SSL EOF、远端关闭连接等；轻量 prompt 能降低输出负担，但不能完全抵消当前接口窗口慢的问题
3. 少量 JSON 解析错误和 `list index out of range` 需要在后续错误重跑或脚本健壮性中处理
4. `MEASURED_BY` 仍是最敏感关系类型，需要在批量结果中持续抽样复核
5. `illegal_relation_pair` warning 数量较高，说明模型仍会提出一批非法边，但当前校验层已能过滤

当前主要错误类型：

- `The read operation timed out`
- `SSL: UNEXPECTED_EOF_WHILE_READING`
- `Remote end closed connection without response`
- 少量 JSON 格式错误

当前高频 warning：

- 重校验前：`weak_evidence_text` 与多类 `illegal_relation_pair`
- 重校验后：主要残留为少量 `illegal_relation_pair:MEASURED_BY:Condition->Mechanism` 和研究模态临床信号不足 warning

这些 warning 不代表最终图谱一定污染，但提示后续质量评估应优先抽查：

- 筛查/诊断工具关系
- 研究模态工具关系
- 干预适用症状关系
- 年龄段与工具/干预关系

## 当前执行策略

为避免批量抽取长期停滞，当前采用“吞吐优先、质量后处理兜底”的策略：

1. 主干覆盖优先：
   - 默认继续尝试新 chunk
   - 不在每个失败 chunk 上长时间重试
   - 失败记录保留，后续集中 retry
2. 质量控制后移：
   - 每轮仍执行 `revalidate`
   - 使用规则层过滤算法类工具、泛研究模态误边和非法关系类型
   - 归一化和 Neo4j 导出只基于重校验后的结果
3. retry 分阶段执行：
   - 接口状态差时少 retry，避免浪费时间
   - 接口状态好或离峰时集中跑 timeout retry
4. 推荐命令：
   - 吞吐推进：`MODE=throughput bash scripts/extraction/run_next_extraction_batch.sh`
   - 稳健推进：`MODE=balanced bash scripts/extraction/run_next_extraction_batch.sh`
5. 模型调用配置入口：
   - URL：`LLM_BASE_URL`
   - API key：`LLM_API_KEY`
   - 模型名：`LLM_MODEL`
   - 输出上限：`MAX_TOKENS` 或 `LLM_MAX_TOKENS`
   - prompt：`SYSTEM_PROMPT`
   - JSON mode：`RESPONSE_FORMAT` 或 `LLM_RESPONSE_FORMAT`

## 下一步开发路径

### 第 1 步：同步当前抽取进度

目标：让 `merged -> normalized -> neo4j_import` 追上当前真实抽取进度。

状态：已完成。

要做：

1. 重新合并：
   - `data/processed/extraction_full_ab_nonbook_v5/chunk_extractions.jsonl`
   - `data/processed/extraction_full_ab_nonbook_v5_retry/chunk_extractions.jsonl`
2. 覆盖或生成新的 `data/processed/extraction_full_ab_nonbook_v5_merged.jsonl`
3. 确认合并后约为：
   - `691` 行
   - `545` ok
   - `146` error

相关脚本：

- `scripts/extraction/merge_extraction_runs.py`

### 第 2 步：生成 current 归一化与 Neo4j 导出

目标：产出比 `partial372` 更新的一组图谱导入文件。

状态：已完成，当前推荐使用 `current_revalidated`。

建议输出目录：

- `data/processed/normalized_full_ab_nonbook_v5_current_revalidated`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated`

相关脚本：

- `scripts/extraction/normalize_extractions.py`
- `scripts/graph/export_neo4j_import.py`

### 第 3 步：做当前批次质量评估

目标：决定是否继续直接跑主干，还是先对 prompt/校验规则做小修。

状态：已完成初版，并据此完成一轮规则修正。

重点看：

- `MEASURED_BY` 精度
- `INDICATED_FOR` 精度
- 证据句是否可回溯
- `illegal_relation_pair` 是否只是被过滤后的残留 warning
- 网络错误是否可通过 retry 收敛

建议产物：

- 当前批次统计摘要：`data/processed/extraction_full_ab_nonbook_v5_current_revalidated_report/summary.json`
- 抽样人工复核清单：`data/processed/extraction_full_ab_nonbook_v5_current_revalidated_report/relation_samples.csv`

### 第 4 步：继续推进 7568 主干抽取

目标：完成 `A/B + 非书籍 + 去噪` 主干语料的批量抽取。

状态：进行中，已新增轻量 prompt 与请求限长入口；当前建议等接口延迟恢复后继续小批次推进。

相关脚本：

- `scripts/extraction/run_full_extraction_batches.sh`
- `scripts/extraction/rerun_timeouts_and_merge.sh`

建议策略：

- 继续 `resume + start-index` 分段推进
- 接口慢时使用 `MODE=throughput BATCH_SIZE=10-25 REQUEST_TIMEOUT=60 MAX_RETRIES=0`
- 接口恢复时使用 `MODE=throughput BATCH_SIZE=50` 扩大覆盖
- 集中 retry 时使用 `scripts/extraction/rerun_timeouts_and_merge.sh`，并保留 `MAX_TOKENS=1200`
- 每增加一批后执行一次 retry
- 每阶段重新 merge
- 周期性跑 normalization 和 Neo4j export
- 不在主干稳定前启动 embedding

### 第 5 步：Neo4j 实入库与查询验证

前置条件：

- 主干抽取完成或至少达到足够规模
- current 版归一化和 Neo4j 导出稳定
- 抽样质量通过

要做：

1. 已完成：准备 Neo4j import CSV 和 Cypher loader
2. 已完成：写基础 Cypher 查询样例
3. 已完成：用 Docker Compose 启动本地 Neo4j 并启用 APOC
4. 已完成：挂载 current CSV 到 Neo4j import 目录
5. 已完成：执行 `load_current.cypher`
6. 已完成：执行 `validation_queries.cypher` 验证核心问题能查到合理子图
7. 下一步：基于验证查询结果继续抽样清理研究模态类 `MEASURED_BY` 噪声

### 第 6 步：embedding 与向量库

前置条件：

- 图谱结构稳定
- chunk/evidence 可回溯

建议对象：

- chunk text embedding
- entity card embedding
- relation/evidence summary embedding

此阶段之后再进入：

- Graph + vector hybrid retrieval
- LangChain/LangGraph 编排
- KGRAG 问答原型
- 模式路由与安全护栏

## 近期推荐执行顺序

1. 已完成：重新生成 `extraction_full_ab_nonbook_v5_merged.jsonl`
2. 已完成：生成 `extraction_full_ab_nonbook_v5_merged_revalidated.jsonl`
3. 已完成：生成 `normalized_full_ab_nonbook_v5_current_revalidated`
4. 已完成：生成 `neo4j_import_full_ab_nonbook_v5_current_revalidated`
5. 已完成：生成当前批次质量统计与抽样复核清单
6. 进行中：用 `scripts/extraction/run_next_extraction_batch.sh` 小批次继续推进主干抽取，当前优先 `MODE=throughput`
7. 下一步：对 timeout/error 执行 `rerun_timeouts_and_merge.sh`
8. 下一步：每个阶段重新 revalidate、normalize、export、summarize
9. Neo4j 当前基线已入库验证；主干抽取覆盖率进一步提升后，再进入 embedding 与 KGRAG 查询原型

## 当前结论

`前处理、真实模型抽取、归一化、Neo4j 导出和本地 Neo4j 入库验证均已跑通；已同步并重校验当前 815 条主干抽取结果。本轮已补齐轻量 prompt、max_tokens、response_format 和 timeout retry 覆盖，确认当前不是配置失效，而是真实抽取请求在该接口窗口仍偏慢。下一步应在接口状态较好时继续 MODE=throughput 小批次扩大覆盖，并周期性执行 refresh_current_outputs.sh 刷新 merge、revalidate、normalize、export、summarize。`
