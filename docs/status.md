# ASD-KGRAG 项目状态记录

更新时间：2026-07-09

---

## 一、总体判断

ASD-KGRAG 已经从“离线建库 + 问答原型”推进到“可运行、可评估、可观测、可协作维护”的阶段。

当前系统已经具备：

- 完整离线数据管线：文献提取、清洗、分块、实体关系抽取、归一化、Neo4j/Qdrant 入库。
- 稳定 KGRAG 问答链路：Neo4j 图谱召回 + Qdrant 向量召回 + 证据 prompt + LLM 生成。
- Dashboard 管理后台：图谱浏览、Chunk 浏览、评估题集、评估运行、别名管理、系统设置、学生返还文件处理。
- QA 评估体系：50 题 dry-run 基线、安全/边界真实生成小样本、端到端 smoke。
- Agent 调度框架：工具化、路由、策略、受控补检索、trace、API `agent_mode`、baseline vs agent 对比评测。

当前最重要的工程判断：

```text
Agent 化的主要价值不是直接提升回答质量，而是统一入口、调度策略、前后处理和可观测性。
真正决定回答质量上限的主因仍然是数据质量、图谱结构、检索组织、alias/query rewrite、rerank 和证据组织。
```

因此，Agent 化目前已经达到“可用调度框架”的阶段。后续质量提升主线应切回数据治理、检索诊断和证据组织优化。

---

## 二、当前进度总览

| 模块 | 进度 | 当前状态 |
|------|------|----------|
| 数据提取 | 100% | 456 篇文档完成解析；抽取输入主干 7568 chunks |
| 数据清洗 | 100% | A/B 主干已形成；C/D 低质量资料已降权/标记 |
| 分块 | 100% | 结构化 chunk 资产完成；Qdrant 写入 7568 points |
| 元数据补全 | 100% | title/year/source_type/evidence_level/include_flag/license 可用 |
| 实体关系抽取 | 100% | 7568/7568 成功；失败重试已清零 |
| 归一化 + Neo4j 入库 | 100% | 当前图谱约 3684 实体、17816 总关系、7568 Chunk |
| Embedding + Qdrant | 100% | `BAAI/bge-small-zh-v1.5`，collection: `asd_kgrag_chunks` |
| KGRAG CLI/API | 100% | `kgrag_answer.py` 与 FastAPI `/ask` 可用 |
| Dashboard | 100% | 管理后台、图谱浏览、评估管理、别名管理、系统设置完成 |
| 评估体系 | 100% | 50 题 dry-run、真实生成小样本、e2e smoke 完成 |
| Agent 调度框架 | 90% | A1-A5 完成；MCP 服务化和更多对比模式待扩展 |
| 数据/检索质量优化 | 进行中 | 下一阶段主线，重点是诊断工具、rerank、图谱/alias 治理 |

全链路成熟度判断：**约 90%**。

说明：这里的 90% 不是指数据管线未完成，而是指系统已经可演示、可评估、可维护，但距离“高质量长期迭代产品”还需要继续做检索诊断、数据治理、对比评测扩展和 Dashboard 可观测性增强。

---

## 三、数据与知识库现状

### 数据资产

- 原始文献与处理资产位于 `data/`，不进入 git。
- 关键可重建资产：
  - `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/`
  - `data/processed/chunks_extractable_full_ab_nonbook.jsonl`
  - `data/backups/`
  - `data/student_returns/`

### Neo4j 图谱

当前运行图谱规模：

- Entity：约 3684
- Chunk：7568
- Evidence：7568
- 总关系：约 17816
- 实体语义关系：约 978

已完成：

- 保守实体合并。
- `config/graph/curated_entity_alias_map.json` 显式 alias 合并。
- `qa_usage`、`tool_category`、证据等级等可用于问答护栏的字段。
- 检索层图谱降噪，不直接粗暴改写 Neo4j 数据。

仍需关注：

- 孤立实体、单 chunk 实体和低置信实体仍然较多。
- 部分关系 `support_count` 高但语义泛化，需要 route-aware rerank。
- 评估工具版本边界，如 ADOS / ADOS-2 / ADI-R / M-CHAT-R/F，仍需保守处理，不能简单合并。

### Qdrant 向量库

- Collection：`asd_kgrag_chunks`
- Points：7568
- Embedding：`BAAI/bge-small-zh-v1.5`
- 当前策略：不重建向量库，优先通过 query rewrite、多查询召回、alias 扩展和融合排序改进召回。

---

## 四、问答与评估现状

### KGRAG 问答链路

默认链路：

```text
query
  -> auto keywords
  -> graph/query alias expansion
  -> Neo4j entity/relation/evidence retrieval
  -> Qdrant multi-query vector retrieval
  -> graph + vector merge
  -> dense keyword-window chunk trim
  -> evidence prompt
  -> LLM answer
```

关键入口：

- CLI：`scripts/qa/kgrag_answer.py`
- API：`scripts/qa/kgrag_api.py`
- 评估：`scripts/qa/evaluate_qa.py`
- e2e：`scripts/qa/e2e_check.sh`

### 当前评估基线

- 50 题 dry-run：`50/50`
- 安全/边界真实生成小样本：`8/8`
- 评估工具版本边界真实生成小样本：`5/5`
- 中文自然问法真实生成小样本：`5/5`
- 最新完整 dry-run 参考：`data/qa_eval/20260708_222608_dry_run`
- 最新 quick dry-run 参考：`data/qa_eval/20260709_144948_dry_run`

### 当前 e2e 覆盖

`scripts/qa/e2e_check.sh` 当前覆盖：

- Python 静态编译。
- JSON/JSONL 基础检查。
- Neo4j/Qdrant 启动与数据检查。
- Neo4j ready 等待，避免 Bolt 刚启动时 handshake 误报。
- FastAPI `/health`。
- 默认 `/ask` dry-run。
- `/ask agent_mode=true` dry-run。
- CLI dry-run。
- Agent CLI dry-run + trace 步骤检查。
- baseline vs agent compare smoke。
- 批量 dry-run。
- 可选真实生成 smoke：`--with-real`。

---

## 五、Agent 化现状与定位

### 已完成

| 阶段 | 状态 | 说明 |
|------|------|------|
| A1 工具化检索 | 已完成 | `agent_tools.py` 封装 route/retrieve/inspect/draft/validate |
| A2 受控补检索 | 已完成 | 最多 1 次 follow-up retrieval，避免自由循环 |
| A3 查询路由 | 已完成 | `agent_router.py` 输出 route、retrieval_focus、guardrail/followup 建议 |
| A4 策略决策 | 已完成 | `agent_policy.py` 输出 answer_mode、forbidden_claims、边界要求 |
| A5 对比评测 | 已完成第一版 | `evaluate_compare.py` 对比 baseline KGRAG 与 agent KGRAG dry-run |
| API 接入 | 已完成 | `/ask` 支持 `agent_mode` 和 `include_trace` |

### Agent 的正确定位

Agent 层现在应被理解为：

```text
统一编排层 / 调度层 / 策略层 / trace 层 / 后续扩展入口
```

它不是回答质量的主要来源。回答质量更依赖：

- 图谱数据质量。
- alias/query rewrite。
- 图谱关系 rerank。
- 向量召回质量。
- graph evidence 与 vector evidence 的组织方式。
- prompt 中证据呈现与引用约束。
- 低质量关系和研究背景关系的降权。

### Agent compare 结果解释

全量 `evaluate_compare.py` 结果：

- 输出目录：`data/qa_compare/20260709_150733_dry_run_compare`
- total：50
- agent_improved：0
- agent_regressed：0
- agent_tied：50
- followup_triggered：0
- relation_delta.avg：0.0
- elapsed_delta_seconds.avg：-0.06

解释：

当前 50 题评估集大多带有人工 `keywords`，baseline KGRAG 已经可以直接命中图谱证据。因此 agent 的补检索条件没有触发，最终全部 tie。这不是 agent 失败，而是说明：

- baseline 检索在当前评估集上已经足够强。
- agent mode 没有引入退化。
- 现有评估集不适合衡量 agent 在“自然无关键词场景”下的调度收益。

后续如果要衡量 agent 调度收益，应扩展 `evaluate_compare.py` 支持忽略人工关键词或使用自然问法集。

---

## 六、Dashboard 与协作现状

Dashboard 已完成：

- 聊天问答界面。
- 图谱概览。
- 实体浏览。
- 关系浏览。
- Chunk 浏览。
- 图谱可视化。
- 使用说明。
- 评估题集管理。
- 评估运行历史。
- 别名管理。
- 系统设置。
- 学生返还 CSV 上传、校验、合并。

当前不足：

- Dashboard 尚未展示 agent route / answer_mode / trace summary。
- Dashboard 尚未展示 compare run。
- 评估运行页目前主要面向 `evaluate_qa.py` 输出，尚未纳入 `evaluate_compare.py` 的 baseline vs agent delta。

---

## 七、主要风险与下一阶段主线

### 当前风险

1. 检索质量风险
   对自然问法、隐含意图、多主题问题，仍可能依赖 alias/query rewrite 和图谱 rerank 的质量。

2. 图谱噪声风险
   孤立实体、单 chunk 实体、低置信关系仍可能污染 graph retrieval。

3. 评估覆盖风险
   当前 50 题基线对 baseline 比较友好，不能完全覆盖真实用户自然问法。

4. 策略表达风险
   `agent_policy.py` 仍是规则系统，需要持续通过真实生成样本验证是否过度护栏或护栏不足。

5. 可观测性风险
   Agent trace 已有，但还没有进入 Dashboard；定位线上问题仍需要看 JSON。

### 下一阶段建议：R1 检索质量与数据组织优化

下一阶段不建议继续围绕“agent 是否显著提升”打转，而应进入：

```text
R1: Retrieval Diagnostics + Data/Rerank Quality
```

建议拆解：

- **R1-1 检索诊断工具**
  对单 query 输出 auto keywords、expanded aliases、matched entities、filtered entities、relations、graph evidence chunks、vector hits、final contexts。

- **R1-2 自然问法评估集**
  新增无人工 keywords 的自然 query set，覆盖家长问法、老师问法、临床边界问法。

- **R1-3 route-aware relation rerank**
  assessment / intervention / risk / safety 使用不同关系优先级，降低泛实体和弱关系干扰。

- **R1-4 数据治理候选清单**
  输出高频低质实体、单 chunk 实体、跨类型 alias 冲突、research_context_only 高风险关系，供人工审核。

- **R1-5 compare 扩展**
  `evaluate_compare.py` 增加 `--ignore-question-keywords`，并逐步扩展 graph-only / vector-only / pure-llm baseline。

---

## 八、当前推荐路线

短期优先级：

1. 提交当前文档更新。
2. 实现 `evaluate_compare.py --ignore-question-keywords`，重新跑 50 题 compare。
3. 新增 retrieval diagnostics 脚本，优先服务数据/检索质量分析。
4. 基于 diagnostics 结果优化 route-aware relation rerank。
5. 再考虑 Dashboard 展示 agent trace 和 compare run。

中期优先级：

1. Dashboard 接入 compare run。
2. 前端问答增加 `agent_mode` 开关。
3. 数据治理候选审核流进入 Dashboard。
4. MCP 服务化。

后续不建议优先投入：

- 复杂自由自治 agent。
- 大规模 LangGraph 重构。
- 在缺少诊断数据前重建 embedding。
- 在没有收益评估前扩大图谱自动合并规则。
