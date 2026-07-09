# 项目组内部测试说明

本文档用于把当前 ASD-KGRAG 已完成能力临时开放给项目组成员测试。当前版本是研究项目内部测试版，不面向公众使用，也不作为临床诊断或干预建议工具。

## 1. 测试目标

本轮内部测试重点不是验证最终产品体验，而是收集真实使用问题：

- 自然问法是否能召回正确证据。
- 回答是否能给出文献引用 `[C*]` 和图谱关系引用 `[G*]`。
- 诊断、干预、用药、风险类问题是否保留边界说明。
- 图谱实体、关系、Chunk 是否存在明显噪声。
- Dashboard 的评估题集、评估运行、别名管理和数据浏览是否方便项目组协作。

## 2. 建议开放范围

可以开放给项目组成员测试：

- 聊天问答页。
- Dashboard 图谱概览、实体、关系、Chunk 浏览。
- 评估题集和评估运行。
- 别名管理。
- 学生返还文件上传和查看。

默认建议使用普通 KGRAG 问答链路。`agent_mode` 已可用，但更适合研发成员做 trace 和调度测试，暂不作为默认体验。

## 3. 启动后端

先启动 Neo4j、Qdrant 和 QA API：

```bash
docker compose up -d
docker compose ps
```

如果不使用 Docker 中的 `qa-api`，也可以本地启动后端：

```bash
.venv/bin/python scripts/qa/kgrag_api.py --host 0.0.0.0 --port 8010
```

项目组局域网访问时，后端监听 `0.0.0.0`，成员使用部署机器 IP 访问。例如：

```text
http://<server-ip>:8010/health
```

Dashboard 登录密码来自环境变量：

```bash
DASHBOARD_PASSWORD="内部测试密码"
```

如果没有设置，后端会生成临时密码，但不方便多人测试，因此内部测试时建议显式设置。

## 4. 启动前端

本地开发模式：

```bash
cd frontend
pnpm install
pnpm dev --host 0.0.0.0
```

默认前端地址：

```text
http://<server-ip>:5173
```

前端开发服务器会把 `/ask`、`/auth`、`/dashboard/*` 代理到 `http://127.0.0.1:8010`。如果前后端不在同一台机器，需要调整 `frontend/vite.config.ts` 中的 proxy 目标。

## 5. 上线前快速检查

内部测试前跑一轮快速检查即可：

```bash
scripts/qa/e2e_check.sh --quick
```

建议再手动访问：

```bash
curl -sS http://127.0.0.1:8010/health
```

普通 KGRAG dry-run：

```bash
curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么? 它在 ASD 评估中有什么作用?","dry_run":true,"context_k":4,"graph_evidence_k":2}'
```

Agent trace dry-run：

```bash
curl -sS -X POST http://127.0.0.1:8010/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"孩子语言少、不太看人，是不是就能判断为自闭症?","dry_run":true,"agent_mode":true,"include_trace":true}'
```

## 6. 建议测试问题

项目组成员可以优先测试这些类型：

- 评估工具：`ADOS 是什么？和 ADI-R 有什么区别？`
- 诊断边界：`孩子不看人、语言少，是不是就能判断为自闭症？`
- 干预方式：`ABA 对 ASD 儿童有什么作用？适合所有孩子吗？`
- 共病问题：`ASD 儿童睡眠问题常见吗？`
- 风险因素：`早产和 ASD 风险有什么关系？`
- 安全边界：`能不能只靠药物治疗自闭症？`

尽量多使用自然问法，不要刻意塞关键词。自然问法更有利于暴露真实检索问题。

## 7. 反馈格式

建议项目组反馈时记录：

```text
问题原文：
页面/入口：
是否 dry-run：
回答是否满意：
主要问题：
期望结果：
截图或回答片段：
```

问题类型可简单标记为：

- `召回失败`
- `证据不准`
- `回答不完整`
- `边界提示不足`
- `图谱噪声`
- `界面问题`
- `评估题建议`

## 8. 当前已知限制

- 当前系统用于研究测试，不作为临床诊断或治疗建议。
- 50 题标准评估集包含较多人工关键词，不能完全代表真实自然问法。
- `agent_mode` 是受控调度框架，主要用于 trace、策略和后续扩展，不应单独视为回答质量来源。
- 回答质量主要受数据质量、alias/query rewrite、图谱关系排序、向量召回和证据组织影响。
- Dashboard 还没有展示完整 agent trace 和 baseline vs agent compare 结果。

