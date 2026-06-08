# ASD-KGRAG

ASD 领域知识图谱 RAG 系统：文档→清洗→分块→实体关系抽取→Neo4j 图谱+Qdrant 向量库→混合检索→问答。

## 当前进度

| 阶段 | 进度 |
|------|------|
| 数据提取 | 100% |
| 清洗 | 100% |
| 分块 | 100% |
| 元数据补全 | 100% |
| 实体关系抽取 | 100% (7568/7568) |
| 归一化+Neo4j 入库 | 100% |
| Embedding+Qdrant | 100% |
| 混合检索原型 | 100% |
| KGRAG 问答原型 | 55% |

状态详情：`docs/status.md`

## 快速启动

--- #1 score=0.6881 ---
  chunk_id: 0e00f768e89e6d99_c0020
  title: Assessment of Autism Spectrum Disorder
  year: 2023
  evidence_level: B
  source_type: article
--- #2 score=0.6770 ---
  chunk_id: 0e00f768e89e6d99_c0007
  title: Assessment of Autism Spectrum Disorder
  year: 2023
  evidence_level: B
  source_type: article
--- #3 score=0.6552 ---
  chunk_id: dfa342e081bd066e_c0004
  title: Autism Spectrum Disorders in Adulthood—Symptoms, Diagnosis, and Treatment
  year: 2024
  evidence_level: B
  source_type: article
--- #4 score=0.6056 ---
  chunk_id: a5e206dfaf35687c_c0066
  title: 自闭症谱系障碍的早期筛查工具
  year: 2022
  evidence_level: B
  source_type: article
--- #5 score=0.5892 ---
  chunk_id: a5e206dfaf35687c_c0067
  title: 自闭症谱系障碍的早期筛查工具
  year: 2022
  evidence_level: B
  source_type: article
graph: 8 entities, 4 relations, 115 chunks
vector: 20 hits

=== Query: ADOS自闭症诊断观察量表 ===
Graph entities found:
  ADOS (AssessmentTool)
  ADOS-2 (AssessmentTool)
  ADOS-Generic (AssessmentTool)
  ADOS-Toddler (AssessmentTool)
  ADOS-Toddler module (AssessmentTool)
  Pre-linguistic ADOS (AssessmentTool)
  ADOS (AssessmentTool)
  ADOS-2 (AssessmentTool)

Graph relations:
  [ent_c423ff86e708]-MEASURED_BY->孤独症 (Condition)
  [ent_aa708b928f94]-MEASURED_BY->孤独症 (Condition)
  [ent_8aa094954adc]-MEASURED_BY->孤独症 (Condition)
  [ent_ee6cb69c2135]-MEASURED_BY->孤独症 (Condition)

Merged results (top 10):
  1. [V]   score=0.4567 evid=B 自闭症谱系障碍的早期筛查工具
  2. [V]   score=0.4292 evid=B 国内同伴介入法提升孤独症儿童社交能力的研究现状与展望
  3. [V]   score=0.4277 evid=B 自闭症谱系障碍的早期筛查工具
  4. [V]   score=0.4234 evid=B 国内同伴介入法提升孤独症儿童社交能力的研究现状与展望
  5. [V]   score=0.4190 evid=B 近十年国际孤独症早期干预研究热点——基于Web of Science期刊文献的可视化分析
  6. [V]   score=0.4180 evid=B 自闭症谱系障碍的早期筛查工具
  7. [V]   score=0.4160 evid=B 婴幼儿早期神经发育障碍的研究进展
  8. [V]   score=0.4148 evid=B 儿童孤独症谱系障碍医学治疗与教育干预综述
  9. [V]   score=0.4009 evid=B 自闭症谱系障碍的社会功能障碍：触觉与催产素
  10. [V]   score=0.3997 evid=B 自闭症谱系量表的理论研究与临床应用

## 模型调用配置



## 基础设施

| 服务 | 端口 | 认证 |
|------|------|------|
| Neo4j | 7474, 7687 | neo4j / asd-kgrag-local |
| Qdrant | 6333, 6334 | 无 |

## 目录结构

- `scripts/extraction/` 数据提取、实体关系抽取、归一化
- `scripts/embedding/` embedding 写入与搜索
- `scripts/retrieval/` 混合检索
- `scripts/qa/` KGRAG CLI 问答原型
- `scripts/graph/` Neo4j 导出、Cypher 生成
- `scripts/cleaning/` 数据清洗
- `scripts/chunking/` 分块
- `scripts/metadata/` 元数据补全
- `docs/` 文档
- `docker-compose.yml` Neo4j + Qdrant
- `.venv/` Python 虚拟环境（sentence-transformers, qdrant-client, neo4j）
