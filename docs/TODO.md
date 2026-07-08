# ASD-KGRAG 现状与后续发展

更新时间: 2026-07-08

---

## 一、已完成

### Phase 0 — 基础设施

- [x] 文献资料 → 文档提取 → 清洗 → 分块 → 实体关系抽取 → 归一化
- [x] Neo4j 图谱入库 (3684 实体, 17816 关系, 7568 Chunk)
- [x] Qdrant 向量库 (asd_kgrag_chunks 集合)
- [x] BAAI/bge-small-zh-v1.5 embedding 模型
- [x] KGRAG CLI + HTTP API 跑通
- [x] FastAPI 迁移 + 连接池 (lifespan-managed Neo4j driver / Qdrant / SentenceTransformer)
- [x] Docker Compose 编排 (Neo4j + Qdrant)
- [x] QA 基础链路 (hybrid_search + answer_query + evaluate_qa)

### Phase 1 — 前端 Dashboard (基础)

- [x] React 18 + Vite+ + Tailwind CSS + ECharts SPA
- [x] 聊天问答界面 (含图谱证据路径/文献引用展示)
- [x] 知识图谱概览 (实体/关系/Chunk 统计 + 类型分布图表)
- [x] 实体浏览 (分页/搜索/类型过滤)
- [x] 关系浏览 (分页/实体过滤/qa_usage 展示)
- [x] Chunk 浏览 (分页/证据等级过滤/文本预览)
- [x] 力导向图谱可视化 (ECharts)
- [x] 使用说明文档页

### Phase 2 — 评估与配置

- [x] 问答模型运行时配置 (qa_settings.json, 即时生效)
- [x] 评估模型列表管理 (CRUD + 启用/禁用)
- [x] 评估题集管理 (CRUD + 关键词/图谱术语/护栏标记)
- [x] CSV 批量导入题集 (QAQUESTION / SAFETYQUESTION 格式)
- [x] 评估运行触发 + 历史查看
- [x] 评估运行详情 (每题 5 项 check + metric + 答案/上下文展开)
- [x] 失败案例筛选 + 状态标记 (待修复/已确认/已修复)
- [x] 运行记录归档 (前端 localStorage 隐藏, 后端保留)
- [x] 评估模型表单补全 (api_key + timeout + max_tokens + 编辑对话框)
- [x] 系统设置页 (问答模型 + 评估模型)

### Phase 2.5 — 协作与数据管理

- [x] 学生协作工作流 (5 种任务模板: QAQUESTION / SAFETYQUESTION / ALIAS / QAREVIEW / CHUNKREVIEW)
- [x] CSV 上传 → 校验 → 解析 → 合并 pipeline (return_store.py)
- [x] 实体别名管理页 (搜索/编辑/新增/候选审核)
- [x] 使用说明全面更新 (10 个模块全覆盖)

---

## 二、待推进

### P0 阻塞性 — 评估基线

- [x] **P0-1 扩评估题集到 30-50 题** — 已扩到 50 题，覆盖 assessment / intervention / comorbidity / risk / safety / qa_boundary / query_quality 七类。最新 dry-run 基线：50/50。
- [x] **P0-2 批评估性能优化** — CLI 批评估已复用 embedding model / QdrantClient / Neo4j driver。50 题 dry-run约半分钟内完成。

### P1 可信度

- [x] **P1-1 拒答/护栏评估指标** — `evaluate_qa.py` 已加入护栏触发检测。安全/边界真实生成小样本 8/8 通过。
- [x] **P1-2 research_context_only 误用检测** — 已加入研究边界与临床过度表述检测，并对否定句做误判规避。

### P2 召回/截断质量

- [x] **P2-1 中文查询质量改善** — 已加入 deterministic query rewrite / 多查询向量检索，不更换 embedding、不重建 Qdrant；新增 5 道中文自然问法评估题，dry-run 50/50，query_quality 真实生成 5/5。
- [x] **P2-2 图谱降噪 + alias 补全** — 已补 query-only alias map，覆盖 ADOS/ADOS-2、ADI-R、M-CHAT/R/F、CARS、ABC、DSM、SRS、SCQ、AQ，以及 ADI-R / EIBI / 家长培训 / 早产围产期 / 药物 / 高压氧等高价值查询；检索层已加入实体去重、具体关键词优先、质量字段降噪和类型意图加权，不直接改写 Neo4j 图谱数据。
- [x] **P2-3 prompt 截断策略改进** — `trim_text` 已改为按关键词命中最密集区间截取，避免长 chunk 中首个弱命中遮蔽后续关键证据。

### P3 工程化

- [x] **P3-1 端到端 smoke 脚本** — `scripts/qa/e2e_check.sh` 已串起静态检查、Neo4j/Qdrant health/data check、FastAPI `/health` + `/ask` dry-run、CLI dry-run、批评估 dry-run；`--with-real` 可选跑安全/边界真实生成 smoke。

### Agent 化 (暂搁)

- [ ] **A1 工具化检索** — 检索包装为 function-calling tools
- [ ] **A2 多步迭代检索** — query rewrite + sub-question + retrieve-evaluate-retrieve
- [ ] **A3 查询路由** — 分流器: 知识问答 / 干预建议 / 安全拒答
- [ ] **A4 独立拒答决策器** — 分类器替代纯 prompt 护栏
- [ ] **A5 对比评测框架** — 纯 LLM vs 纯 RAG vs KGRAG
- [ ] **A6 MCP 服务化** — QA 能力暴露为 MCP server
- [ ] **A7 FastAPI + 容器化** — 已完成 (FastAPI 迁移完毕)

---

## 三、当前架构

```
前端 (React 18 + Vite+ + Tailwind)
  ├── 聊天问答 (ChatApp)
  └── Dashboard SPA
       ├── 概览          ← Neo4j 统计
       ├── 实体浏览       ← Neo4j 实体列表
       ├── 关系浏览       ← Neo4j 关系列表
       ├── Chunk 浏览     ← Neo4j chunk 列表
       ├── 图谱可视化     ← ECharts 力导向图
       ├── 使用说明       ← 静态文档
       ├── 评估题集       ← JSONL CRUD + CSV 批量导入
       ├── 评估运行       ← 运行历史/详情/归档
       ├── 别名管理       ← alias_map JSON CRUD
       └── 系统设置       ← qa_settings.json

后端 (FastAPI :8010)
  ├── /ask              ← KGRAG 问答
  ├── /auth/*            ← HMAC token 认证
  ├── /dashboard/stats   ← 图谱统计
  ├── /dashboard/entities/relations/chunks ← 数据浏览
  ├── /dashboard/graph-data ← 图谱可视化数据
  ├── /dashboard/settings ← 问答模型配置
  ├── /dashboard/eval-models ← 评估模型 CRUD
  ├── /dashboard/eval-questions ← 评估题集 CRUD
  ├── /dashboard/eval/runs ← 运行历史/详情
  ├── /dashboard/returns ← CSV 上传/校验/合并
  └── /dashboard/aliases ← 别名管理

数据层
  ├── Neo4j 5.26        ← 知识图谱
  ├── Qdrant            ← 向量库
  ├── config/qa_settings.json ← 运行时配置
  ├── scripts/qa/eval_questions.jsonl ← 评估题集
  ├── data/qa_eval/     ← 评估运行结果
  ├── data/student_returns/ ← 学生返还文件
  └── config/graph/curated_entity_alias_map.json ← 别名映射
```

## 四、推进顺序建议

```
P0-1 + P0-2  → 先有评估尺子（2-3 天）
P1-1 + P1-2  → 链路可信度（1-2 天）
P2-1 + P2-2 + P2-3 → 召回与截断质量（3-5 天）
P3-1  → 可演示/可交接（1 天）
之后再启动 Agent 化
```
