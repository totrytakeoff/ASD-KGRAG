# 项目组内测部署

## 运行结构

- nginx：80 端口，直接提供 `frontend/dist`，并代理 API/SSE。
- qa-api：Docker Compose 管理，仅监听 `127.0.0.1:8010`。
- Neo4j/Qdrant：Docker Compose 管理，仅监听本机。
- 模型运行配置：`config/qa_settings.json`，不进入 Git。

首次部署前：

```bash
cp config/qa_settings.example.json config/qa_settings.json
cp .env.example .env
```

填写 `.env` 和 `config/qa_settings.json` 中的运行时密钥后执行：

```bash
DEPLOY_ROOT=/opt/asd-kgrag \
COMPOSE_FILE=docker-compose.yml \
SERVER_NAME=your.internal.host \
bash scripts/deploy/internal_deploy.sh
```

离线服务器使用仓库中的 `docker-compose.deploy.yml` 和 `Dockerfile.qa.deploy`。部署前需要在 `wheels/` 准备 `requirements-qa.deploy.txt` 对应 wheels 及 `torch==2.7.1+cpu`，并将 `COMPOSE_FILE` 设为 `docker-compose.deploy.yml`。`SERVER_NAME` 可填写内网域名或服务器 IP。

## 问答模式

| 模式 | Context | 图证据 | 每段字符 | 最大输出 |
|---|---:|---:|---:|---:|
| fast | 2 | 1 | 400 | 500 |
| balanced | 4 | 2 | 600 | 800 |
| deep | 6 | 4 | 900 | 1200 |

聊天页默认使用 `balanced`。显式 API 参数会覆盖 profile 中对应的值。

## 检查

```bash
curl -fsS http://127.0.0.1:8010/health
curl -fsS http://127.0.0.1:8010/health/deep
curl -N -X POST http://127.0.0.1:8010/ask/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"ADOS 是什么?","profile":"balanced"}'
```

Dashboard 的“模型性能”页面可启动 SiliconFlow 候选模型延迟基准。默认任务为 4 个模型、5 道题、平衡模式各运行 1 次；该任务会产生模型调用费用。

交互式问答对 Qwen3 系列关闭 thinking，以避免推理 token 占满输出预算而没有最终正文。模型切换应以平衡模式的成功率、质量检查和延迟结果为依据。

2026-07-10 的 3 题平衡模式筛选中，`Qwen/Qwen3.5-27B` 成功率和质量通过率均为 3/3，TTFT p50/p95 为 0.52/0.53 秒，总耗时 p50/p95 为 26.79/31.52 秒，因此作为当前内测默认问答模型。该结果用于项目组内测选型，不替代后续完整评测。

同日使用禁用检索缓存的 3 题对照中，标准链路与 Agent 链路均为 3/3 成功、3/3 质量通过；Agent p50 总耗时 21.15 秒，标准链路 22.74 秒，门槛通过。因此内测默认启用 Agent 链路；请求显式传入 `"agent_mode": false` 可回退到标准链路。

同日完成当前默认 Agent/Qwen 27B 的 50 题 balanced 真实生成评测：50/50 成功、50/50 质量通过、0 降级、0 重试；TTFT p50/p95 为 0.668/5.053 秒，总耗时 p50/p95 为 22.876/31.578 秒。结果保存在 `data/qa_benchmarks/20260710_093128_cdba82.json`。

## 回滚

代码回滚后重新运行 `scripts/deploy/internal_deploy.sh`。模型或 API 地址配置错误时，只需修正 `config/qa_settings.json`；设置接口保存后即时生效。

当前策略仅停止继续跟踪运行时密钥文件，没有清理历史提交中的旧密钥。公开仓库或扩大协作者范围前应轮换密钥并清理历史。
