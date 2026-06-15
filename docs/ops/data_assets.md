# 数据资产说明

本项目的代码和文档进入 git，但 `data/` 不进入 git。迁移、复现、交接时必须单独同步数据资产。

## 必要数据

最低运行 KGRAG QA 需要：

| 数据 | 路径 | 用途 |
|------|------|------|
| Neo4j 导入包 | `data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated/` | 重建图数据库 |
| Chunk 输入 | `data/processed/chunks_extractable_full_ab_nonbook.jsonl` | 重建 Qdrant 向量库 |

当前 Neo4j 导入包规模：

| 类型 | 数量 |
|------|------|
| Entity | 3684 |
| Chunk | 7568 |
| Evidence | 7568 |
| Entity relations | 978 |
| SUPPORTS | 1702 |
| FROM | 7568 |

## 可选数据

| 数据 | 路径 | 用途 |
|------|------|------|
| 原始文献 | `data/raw/` | 从头重跑提取 |
| 清洗结果 | `data/processed/cleaned_full/` | 重跑分块 |
| 分块结果 | `data/processed/chunks_full/` | 调试 chunking |
| 抽取结果 | `data/processed/extraction_full_ab_nonbook_v5*` | 重跑归一化/图谱导出 |
| QA 评估输出 | `data/qa_eval/` | 保存评估记录 |
| 本地备份 | `data/backups/` | 快速回滚 |
| 学生返还 | `data/student_returns/` | 人工协作数据 |

## 同步建议

推荐把数据包压缩后传输：

```bash
tar -czf asd_kgrag_min_runtime_data_YYYYMMDD.tar.gz \
  data/processed/neo4j_import_full_ab_nonbook_v5_current_revalidated \
  data/processed/chunks_extractable_full_ab_nonbook.jsonl
```

目标机器解压到项目根目录：

```bash
tar -xzf asd_kgrag_min_runtime_data_YYYYMMDD.tar.gz
```

## 不要提交到 git

以下内容不要提交：

- `.env`
- `data/`
- API key
- Docker volume dump
- 大型模型缓存
- 学生返还的原始压缩包

`.gitignore` 已经忽略：

```text
data/
.env
.env.*
```

## 数据重建边界

可以从导入包重建：

- Neo4j 图数据库

可以从 chunk JSONL 重建：

- Qdrant chunk collection

不能只靠 git 重建：

- 原始文献
- 已清洗数据
- 已抽取结果
- 现有数据库 volume

因此，迁移前至少要确认最低运行数据已经同步。
