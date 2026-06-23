# ASD-KGRAG Dashboard — 协作管理后台设计基准

## 定位

Dashboard 是面向协作者（学生/审核员/管理者）的知识图谱内容管理后台，将现有的 CSV/JSONL 文件包往返协作模式升级为**网页端录入 + 自动评估 + 内容审核**的一体化协作平台。

## 鉴权方案

轻量级单密码鉴权，无用户体系：

- `.env` 配置项：`DASHBOARD_PASSWORD`（默认自动生成）
- `POST /auth/login` 校验密码 → 返回 HMAC 签名 token（7 天有效期）
- FastAPI `AuthDep` dependency 校验 `Authorization: Bearer <token>`
- 前端 token 存 `localStorage`，401 跳登录页
- 未来可扩展为多用户 + 操作日志

## 路由结构

```
/                → 现有问答界面（不动）
/login           → Dashboard 登录页
/dashboard       → Dashboard 布局（侧栏 + 内容区）
  ├─ /dashboard/overview         图谱概览（统计 + 最近 eval + 待审核）
  ├─ /dashboard/entities         实体浏览（搜索 + 类型过滤 + 别名）
  ├─ /dashboard/relations        关系浏览（按实体过滤 + support 排序）
  ├─ /dashboard/chunks           Chunk 浏览（metadata + preview）
  ├─ /dashboard/eval-questions   评估题集 CRUD
  ├─ /dashboard/eval-runs        评估运行 + 历史结果
  └─ /dashboard/returns          学生返还文件 + 审核
```

## 后端新增 API

### 认证
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/auth/login` | 密码 → token |
| GET  | `/auth/verify` | 校验 token 有效性 |

### 图谱内容（只读，复用 lifespan 连接）
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/dashboard/stats` | 实体/关系/chunk 计数 + type 分布 |
| GET | `/dashboard/entities` | 分页 + 搜索 + 类型过滤 |
| GET | `/dashboard/relations` | 分页 + 按 source/target 过滤 |
| GET | `/dashboard/chunks` | 分页 + doc_id/evidence_level 过滤 |

### 评估题集管理
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/dashboard/eval-questions` | 列出现有题集 |
| POST | `/dashboard/eval-questions` | 新增题目 |
| PATCH | `/dashboard/eval-questions/:id` | 编辑题目 |
| DELETE | `/dashboard/eval-questions/:id` | 删除题目 |

### 评估运行
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/dashboard/eval/run` | 触发评估运行 |
| GET | `/dashboard/eval/runs` | 历史运行列表 |
| GET | `/dashboard/eval/runs/:id` | 单次运行详情 |

### 学生返还文件
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/dashboard/returns` | 上传 CSV/JSONL 返还文件 |
| GET | `/dashboard/returns` | 列出文件 + 审核状态 |
| PATCH | `/dashboard/returns/:id` | 标记 accepted/rejected |
| POST | `/dashboard/returns/:id/merge` | accepted 题集并入 eval_questions |

## 实施阶段

### Phase 1（当前）
鉴权 + 图谱只读浏览（overview / entities / relations / chunks）

### Phase 2
评估题集 CRUD + eval 手动触发 + 历史结果查看

### Phase 3
学生返还文件上传 + 审核 + 一键并入

### Phase 4
CI/CD 自动触发：题集变更或返还并入后自动跑 dry_run eval

## 涉及文件

| 文件 | 阶段 | 操作 |
|------|------|------|
| `scripts/qa/kgrag_api.py` | 1-4 | 新增 auth + dashboard 路由 |
| `scripts/qa/dashboard_queries.py` | 1 | 新建：Neo4j 查询封装 |
| `scripts/qa/eval_store.py` | 2 | 新建：题集读写 + eval 运行管理 |
| `scripts/qa/return_store.py` | 3 | 新建：返还文件管理 |
| `frontend/src/dashboard/*.tsx` | 1-4 | 新建：Dashboard 组件 |
| `frontend/src/App.tsx` | 1 | 接入 react-router，路由分发 |
| `frontend/src/Login.tsx` | 1 | 新建：登录页 |
| `frontend/package.json` | 1 | 加 react-router-dom |
| `.env` | 1 | 加 DASHBOARD_PASSWORD |
