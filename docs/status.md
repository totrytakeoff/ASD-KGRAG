# 项目状态记录

更新时间：2026-05-27

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
- 已加入：
  - 类型纠偏
  - 关系合法性校验
  - 弱证据过滤
  - 请求重试与退避
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
- 最近两轮吞吐模式分别覆盖 `24` 条和 `16` 条；后一轮 `7` 条成功、`9` 条错误。当前接口状态偏慢，吞吐模式仍适合避免停滞，但成功率会下降
- 最近一轮吞吐模式继续尝试 `10` 条后人工停止，`10` 条均为 timeout/connection 错误；当前接口窗口不适合继续硬跑模型请求
- 已清理可再生/过期中间产物：非重校验 `current` 图谱导出、`partial372` 归一化和 Neo4j 导出、Python `__pycache__`
- 已建立 git 基线提交：`1476018`，并提交 `run_next_extraction_batch.sh` 可执行权限修正：`d1f2661`

### 6. 归一化与 Neo4j 导出

已实现：

- `scripts/extraction/normalize_extractions.py`
- `scripts/graph/export_neo4j_import.py`
- `docs/data_process/graph_export_sop.md`

已验证产物：

- `data/processed/normalized_full_ab_nonbook_v5_partial372`
- `data/processed/neo4j_import_full_ab_nonbook_v5_partial372`
- `data/processed/normalized_full_ab_nonbook_v5_current_revalidated`
- `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated`

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
- 实体：`1719`
- 聚合关系：`351`
- evidence：`616`
- 聚合关系分布：
  - `MEASURED_BY`: `146`
  - `INDICATED_FOR`: `139`
  - `COMORBID_WITH`: `31`
  - `SUITABLE_AGE`: `20`
  - `SUITABLE_SETTING`: `6`
  - `HAS_RISK`: `6`
  - `NOT_INDICATED_FOR`: `3`

`current_revalidated` Neo4j 导出摘要：

- entity nodes：`1719`
- chunk nodes：`7568`
- evidence nodes：`616`
- entity relationships：`351`
- supports relationships：`523`
- from relationships：`616`

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

本轮规则修正：

- 将 `机器学习`、`SVM/SVR`、`支持向量机`、`算法`、`分类器`、`模型` 等从 `AssessmentTool` 倾向中排除
- 对 `EEG/fMRI/sMRI/MRI` 等研究模态收紧 `MEASURED_BY` 保留条件
- 研究模态只有在证据中出现明确诊断性能信号时，才允许作为 `Condition -> MEASURED_BY -> AssessmentTool` 关系进入主图
- 保留 `ADOS`、`ADI-R`、`M-CHAT`、`CARS`、`ABC`、问卷、量表、访谈、观察表等临床筛查/诊断工具关系

## 当前问题与卡点

当前不是基础链路卡住，而是批量生产阶段的同步和稳定性问题：

1. 主干抽取已继续推进，但合并文件、归一化产物、Neo4j 导出产物尚未同步到最新进度
2. 第三方模型接口仍有明显网络错误，包括 timeout、SSL EOF、远端关闭连接等
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

相关脚本：

- `scripts/extraction/run_full_extraction_batches.sh`
- `scripts/extraction/rerun_timeouts_and_merge.sh`

建议策略：

- 继续 `resume + start-index` 分段推进
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

1. 准备 Neo4j import 或 Cypher loader
2. 导入 entity、chunk、evidence 节点
3. 导入实体关系、证据支持关系、chunk 来源关系
4. 写基础 Cypher 查询样例
5. 验证核心问题能查到合理子图

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
9. 主干抽取稳定后再进入 Neo4j 实入库和 embedding

## 当前结论

`前处理、真实模型抽取、归一化和 Neo4j 导出均已跑通；已同步并重校验当前 815 条主干抽取结果。当前模型接口 timeout/SSL 错误偏多，最近一轮吞吐尝试全部失败；建议暂停硬跑模型请求，待接口状态恢复后再用 MODE=throughput 提高覆盖率，并在接口状态较好时集中执行 timeout retry。每个阶段仍按 revalidate、normalize、export、summarize 固定链路刷新。`
