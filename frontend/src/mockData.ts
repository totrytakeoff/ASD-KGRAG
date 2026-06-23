import type { Conversation, Message } from "./types";

// 一段逼真的 ASD-KGRAG 多轮医疗问答 Mock 数据
// 节点和关系参考后端真实 Cypher 结构:Entity / MEASURED_BY / INDICATED_FOR / COMORBID_WITH
const mockMessages: Message[] = [
  {
    role: "user",
    content: "ADOS 是什么?它在 ASD 评估中有什么作用?",
  },
  {
    role: "ai",
    content: `## ADOS(孤独症诊断观察量表)

**ADOS(Autism Diagnostic Observation Schedule)** 是一种标准化的、半结构化的**行为观察评估工具**,用于诊断孤独症谱系障碍(ASD)。

### 在 ASD 评估中的作用

1. **核心诊断工具** — ADOS 是目前国际公认的 ASD "金标准"诊断工具之一 [G1]。
2. **适用年龄广** — 覆盖从幼儿到成人的各年龄段,通过模块化设计适配不同语言与发育水平 [C1]。
3. **半结构化观察** — 评估师通过引发社交、游戏、沟通行为,观察被试反应并按标准化编码打分 [C2]。
4. **不能单独诊断** — ADOS 结果需结合 **ADI-R**(访谈)、发育史、其他认知/语言评估综合判断 [G2]。

### 证据边界

- ADOS-2 是当前主流版本,模块 1-4 对应不同语言能力 [C1]。
- 单独 ADOS 阳性不等于 ASD 确诊,需**多工具联合**与**临床综合判断** [G2]。
- 本回答仅作知识科普,**不能替代专业评估或临床决策**。

> ⚠️ 临床护栏:诊断、干预、用药相关问题请咨询持证专业人员。`,
    relations: [
      {
        source: "孤独症",
        target: "ADOS",
        relation: "MEASURED_BY",
        support_count: 12,
        confidence: 0.92,
      },
      {
        source: "孤独症",
        target: "ADOS-2",
        relation: "MEASURED_BY",
        support_count: 8,
        confidence: 0.88,
      },
      {
        source: "PDDs",
        target: "ADOS",
        relation: "MEASURED_BY",
        support_count: 4,
        confidence: 0.75,
      },
      {
        source: "孤独症",
        target: "ADI-R",
        relation: "MEASURED_BY",
        support_count: 6,
        confidence: 0.85,
      },
    ],
    nodes: [
      { id: "孤独症", name: "孤独症", type: "Condition" },
      { id: "ADOS", name: "ADOS", type: "AssessmentTool" },
      { id: "ADOS-2", name: "ADOS-2", type: "AssessmentTool" },
      { id: "PDDs", name: "广泛性发育障碍", type: "Condition" },
      { id: "ADI-R", name: "ADI-R", type: "AssessmentTool" },
    ],
    citations: [
      {
        citation_id: "C1",
        title: "ADOS-2 临床手册",
        year: 2023,
        evidence_level: "A",
        retrieval: "graph-evidence",
        score: 0,
      },
      {
        citation_id: "C2",
        title: "ASD 标准化诊断流程综述",
        year: 2022,
        evidence_level: "A",
        retrieval: "graph+vector",
        score: 0.81,
      },
    ],
    retrieved_at: new Date().toISOString(),
  },
  {
    role: "user",
    content: "ABA 干预对孤独症孩子效果怎么样?有什么风险吗?",
  },
  {
    role: "ai",
    content: `## ABA(应用行为分析)干预概述

**应用行为分析(ABA)** 是目前循证支持最充分的 ASD 早期行为干预范式之一 [G1]。

### 主要效果

- **正向行为塑造** — 通过 DTT(回合式教学)、PRT(关键反应训练)等方法提升社交、沟通、适应行为 [C1]。
- **强度相关** — 每周 20-40 小时结构化干预,早期介入(2-4 岁)效果更显著 [C2]。
- **个体差异大** — 部分儿童进步明显,部分收益有限,**不能承诺治愈** [G2]。

### 已知风险与争议

1. **过度依赖回合训练** 可能出现技能泛化困难、机械性行为。
2. **早期高强度版本** 引发关于儿童自主性与情绪压力的伦理讨论 [C3]。
3. **干预师资质参差** — 非持证 BCBA 实施可能影响质量与安全 [G2]。

### 证据边界

- ABA 属于**循证干预**,但不是唯一路径,需结合 NDBI、ESDM、言语/OT 等综合方案 [G1]。
- 个体化方案应由**持证行为分析师**与家长、跨专业团队共同制定。

> ⚠️ 临床护栏:本回答仅作知识科普,**不能替代专业评估、干预方案或临床决策**。`,
    relations: [
      {
        source: "应用行为分析",
        target: "孤独症",
        relation: "INDICATED_FOR",
        support_count: 15,
        confidence: 0.9,
      },
      {
        source: "应用行为分析",
        target: "ABA训练法",
        relation: "别名",
        support_count: 3,
        confidence: 0.95,
      },
    ],
    nodes: [
      { id: "应用行为分析", name: "应用行为分析", type: "Intervention" },
      { id: "ABA训练法", name: "ABA训练法", type: "Intervention" },
      { id: "孤独症", name: "孤独症", type: "Condition" },
    ],
    citations: [
      {
        citation_id: "C1",
        title: "NAC 行为干预循证综述",
        year: 2020,
        evidence_level: "A",
        retrieval: "graph-evidence",
      },
      {
        citation_id: "C2",
        title: "Lovaas 早期干预研究",
        year: 1987,
        evidence_level: "B",
        retrieval: "vector",
        score: 0.72,
      },
      {
        citation_id: "C3",
        title: "ABA 伦理与自主性综述",
        year: 2021,
        evidence_level: "B",
        retrieval: "graph+vector",
        score: 0.76,
      },
    ],
    retrieved_at: new Date().toISOString(),
  },
];

export const mockConversations: Conversation[] = [
  {
    id: "c1",
    title: "ADOS 评估作用",
    messages: mockMessages,
    updated_at: new Date().toISOString(),
  },
  {
    id: "c2",
    title: "ABA 干预效果与风险",
    messages: [mockMessages[2], mockMessages[3]],
    updated_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    id: "c3",
    title: "ASD 共病睡眠障碍",
    messages: [],
    updated_at: new Date(Date.now() - 2 * 86400000).toISOString(),
  },
  {
    id: "c4",
    title: "ADOS 与 M-CHAT 区别",
    messages: [],
    updated_at: new Date(Date.now() - 3 * 86400000).toISOString(),
  },
];
