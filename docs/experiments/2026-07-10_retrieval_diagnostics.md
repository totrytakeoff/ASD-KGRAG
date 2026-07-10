# 2026-07-10 自然问法检索诊断实验

## 目标

验证 50 题标准评估集在不使用人工 `keywords` 时的真实检索表现，区分 query rewrite、首轮 KGRAG 和 Agent 补检索各自的作用，并输出后续数据治理候选。

## 设置

- 题集：`scripts/qa/eval_questions.jsonl`，共 50 题、7 个类别。
- Profile：`balanced`，context 4、graph evidence 2、每段 600 字符。
- 自然问法：忽略题目中的人工 `keywords`。
- 诊断任务禁用共享检索缓存。
- 检查：上下文存在、图谱证据存在、预期术语或其 alias 在最终证据中出现。
- 对照：保留人工 keywords 的同配置检索，以及 baseline/Agent dry-run compare。

## 结果

| 阶段 | 自然问法通过 | 主要变化 |
|---|---:|---|
| 初始诊断 | 40/50 | 修正诊断器，使预期术语检查包含 Chunk 正文 |
| 领域提示 rewrite | 46/50 | 提取专业评估、筛查、诊断、家庭/学校、睡眠/ADHD 等隐含概念 |
| alias 与证据语义 | 49/50 | 预期术语支持 alias；citation/evidence level 计入证据语义；补 ASD 域锚点 |
| specificity 优先 | 50/50 | 存在“饮食干预”等具体概念时抑制泛词“干预” |
| 人工 keywords 控制组 | 50/50 | 验证最终自然问法结果已追平控制组 |

最终自然问法诊断目录：

```text
data/retrieval_diagnostics/20260710_095333_balanced_natural_query
```

## Agent 对照

最终无关键词对照结果：

- total：50
- Agent improved：2
- Agent regressed：0
- tied：48
- follow-up triggered：2
- 改善题：`safety_single_symptom_diagnosis`、`query_quality_nonverbal_diagnosis`

输出目录：

```text
data/qa_compare/20260710_092908_dry_run_compare
```

结果表明，query rewrite 解决普遍召回问题；Agent 的可测收益集中在诊断边界问题的补关系检索，没有对其余题目造成退化。

## 失败根因

本轮依次识别并修正了四类问题：

1. 评测口径遗漏 Chunk 正文和 alias，导致正确英文证据被误判。
2. 中文自动关键词将整段会话文本当成实体词，产生“回答课堂问题的正确率提高”等噪声命中。
3. 隐含意图没有映射到图谱词，例如“两三岁筛查”没有映射到 M-CHAT，“好动”没有映射到 ADHD/注意力。
4. 泛词“干预”压过“饮食干预”等具体词，导致普通 Intervention 实体淹没目标证据。

## 数据治理观察

诊断报告仍显示较多需要人工复核的实体：

- 高频 `alias_type_conflict` 和 `same_name_duplicate`。
- 孤立 AssessmentTool 及只有 1 个 Chunk 的派生工具实体。
- `assessment_tool_category:generic_method` / `digital_algorithm` 分类边界。
- 泛 ASD、儿童和干预实体在多类问题中高频参与召回。

治理候选应排除 `merged_by:*` 等已完成合并的审计标记，只保留孤立、低支撑、类型冲突、同名重复和工具分类异常。下一步应先人工抽查高频候选，再决定是否调整 route-aware relation rerank。

当前最高频候选包括：VB-MAPP 工具分类、功能性行为评估/MABC-2/M-ABC2 孤立实体、催产素 alias 类型冲突、儿童同名类型冲突，以及 PEAK/S-S法/ABLLS-R 等 AssessmentTool 分类边界。

## 结论

当前 50 题上，首轮自然问法检索已经追平人工关键词控制组。Agent 正确承担受控补检索角色，但不是主要质量来源。后续实验重点应转向独立口语问法集、数据治理审核和 graph-only/vector-only/pure-LLM 对照，避免继续针对现有题集过拟合。

## 真实生成验证

使用当前线上默认配置 `Qwen/Qwen3.5-27B + balanced + Agent` 串行运行 50 题真实生成：

- 生成成功：50/50
- 质量通过：50/50
- 降级：0
- 重试：0
- TTFT p50/p95：0.668 / 5.053 秒
- 总耗时 p50/p95：22.876 / 31.578 秒
- 最慢总耗时：`intervention_music`，43.674 秒
- 最慢 TTFT：`safety_direct_treatment`，5.832 秒

七个类别均全量通过。结果文件：

```text
data/qa_benchmarks/20260710_093128_cdba82.json
```

该评测证明当前链路在既有 50 题上运行稳定，但质量检查仍是规则型指标，不能替代项目组成员对回答事实正确性、引用充分性和表达质量的人工审核。
