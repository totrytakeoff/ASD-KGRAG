# ASD-KGRAG 项目目标

更新时间：2026-07-09

## 总目标

构建一个面向 ASD 领域的可评估、可维护、可扩展的知识图谱增强 RAG 系统，支持文献证据追溯、图谱关系引用、临床/干预边界提示、学生协作数据回流和后续 Agent/MCP 服务化。

## 当前定位

项目已经完成 KGRAG 主链路、Dashboard、评估体系和受控 Agent 调度框架。当前 Agent 化不再作为质量提升主线，而是作为统一入口、调度策略、前后处理、trace 和后续 MCP 的架构基础。

回答质量后续主要由以下部分决定：

- 数据质量与图谱结构。
- Query alias / rewrite。
- 图谱关系和证据 rerank。
- 向量召回组织。
- 证据上下文压缩与 prompt 组织。
- 安全边界与研究边界后处理。

## 阶段目标

### G1: KGRAG 稳定闭环

状态：已完成。

- 数据提取、清洗、分块、抽取、归一化、Neo4j/Qdrant 入库。
- CLI/API 问答链路。
- 50 题 dry-run 评估基线。
- 安全/边界真实生成小样本。
- 端到端 smoke。

### G2: 管理与协作后台

状态：已完成。

- Dashboard 图谱浏览、Chunk 浏览、评估管理、别名管理、系统设置。
- 学生返还 CSV 上传、校验、合并。
- 评估运行历史与详情查看。

### G3: 受控 Agent 调度框架

状态：已完成第一版。

- 工具化 workflow。
- 查询路由。
- 策略决策。
- 最多一次受控补检索。
- trace。
- `/ask agent_mode`。
- baseline vs agent dry-run compare。

### G4: 检索质量与数据组织优化

状态：下一阶段主线。

- 单 query 检索诊断。
- 无人工关键词自然问法评估集。
- route-aware relation rerank。
- 数据治理候选清单。
- compare 扩展到 ignore-keywords、graph-only、vector-only、pure-LLM。

### G5: 可观测性与服务化

状态：待推进。

- Dashboard 展示 agent trace summary。
- Dashboard 接入 compare run。
- 前端问答支持 agent mode 开关。
- MCP 服务化。

## 暂缓目标

- VLA 方向暂不进入当前工程主线。
- 不优先做自由自治 Agent 或大规模 LangGraph 重构。
- 不在缺少诊断证据前重建 embedding 或扩大自动实体合并规则。
