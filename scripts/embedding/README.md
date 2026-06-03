# Embedding 与向量库

## 作用

将 chunk 文本、entity 卡片等对象编码为稠密向量，存入向量数据库，支持在线问答时的语义相似度检索。

## 架构定位

根据 `docs/guide.md` 的 KGRAG 架构：

- **Neo4j**：结构化图谱存储与子图召回（实体匹配 → 1-hop/2-hop 扩展 → 证据等级/置信度过滤）
- **向量库**：语义相似度搜索（query embedding → top-K 最相近 chunk）
- **混合检索**：图检索先缩小范围 → 向量检索在子图关联 chunk 内做语义召回

两者通过 chunk_id / entity_id 绑定，缺一不可。

## 向量库选型

### 推荐：Qdrant

- 轻量 Docker 部署，单二进制
- Python client 成熟，与 LangChain 生态集成好
- HNSW 索引，支持过滤 + 向量联合查询
- 对 7K 级数据完全够用，后续扩展到百万级也无压力
- Docker Compose 与现有 Neo4j 服务并列管理

### 备选：Neo4j 内置向量索引（5.x）

- 优点：不引入额外服务，图查询与向量查询可在同一 Cypher 中完成
- 缺点：HNSW 参数可调性较弱，ANN 性能不如专用引擎，混合查询语法较重
- 适合：极简部署或数据量很小的场景

当前项目选择 Qdrant，后续如需简化部署可切换到 Neo4j 向量索引。

## Embedding 模型

### 推荐：sentence-transformers/all-MiniLM-L6-v2

- 维度：384
- 速度：CPU 上约 30-50 句/秒
- 语言：英文为主，中文有基本覆盖
- 优点：轻量、无需 GPU、模型体积约 80MB

### 远期升级选项

- BAAI/bge-small-zh-v1.5：中文优化，512 维
- BAAI/bge-m3：多语言，1024 维，更高精度但更慢
- SiliconFlow / OpenAI embedding API：远程调用，省本地资源但依赖网络

## 入库对象

按 guide.md 6.2 节，建议三类：

1. **chunk embeddings**：真实证据文本的向量（优先实现）
2. **entity card embeddings**：实体卡 = 实体名称 + 类型 + 描述 + 关键关系摘要
3. **community summary embeddings**：社区摘要（后续阶段）

每条向量必须带 metadata：
- chunk_id / entity_id / doc_id
- year / evidence_level
- linked_entity_ids[]

## Qdrant Collection 设计

### chunks collection

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | chunk_id |
| vector | float[384] | 文本嵌入 |
| payload.chunk_id | string | 原始 chunk_id |
| payload.doc_id | string | 文档 ID |
| payload.title | string | 文档标题 |
| payload.year | int | 年份 |
| payload.evidence_level | string | A/B/C/D |
| payload.source_type | string | 文献类型 |

### entities collection（后续）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | entity_id |
| vector | float[384] | 实体卡文本嵌入 |
| payload.entity_id | string | 原始 entity_id |
| payload.name | string | 实体名称 |
| payload.type | string | 实体类型 |

## 环境变量

- `EMBEDDING_MODEL`：模型名称，默认 all-MiniLM-L6-v2
- `QDRANT_URL`：Qdrant 服务地址，默认 http://localhost:6333
- `QDRANT_API_KEY`：可选，Qdrant API key

## 依赖

-sentence-transformers
- qdrant-client
- numpy（已有）

## 文件清单

- `scripts/embedding/embed_chunks.py`：chunk 文本嵌入 + 写入 Qdrant
- `scripts/embedding/build_entity_cards.py`：生成 entity 卡片文本
- `scripts/embedding/embed_entity_cards.py`：entity 卡片嵌入 + 写入 Qdrant
- `scripts/embedding/search_chunks.py`：向量相似度搜索脚本（调试用）
