# ALIAS：实体别名候选收集任务

## 任务目标

请收集 ASD 相关工具、量表、干预方法、症状或共病的中文名、英文名、缩写和可能别名。

你只负责收集候选，不负责决定是否合并。

---

## 每人工作量

建议每人负责：

```text
10-15 个实体
```

---

## 重要提醒

有些名字看起来相似，但可能是不同版本，不能随便说它们完全相同。

例如：

- `ADOS` 和 `ADOS-2` 可能需要保留版本区别。
- `M-CHAT`、`M-CHAT-R`、`M-CHAT-R/F` 可能需要保留版本区别。
- `CARS` 和 `CARS-2` 可能需要保留版本区别。
- `SRS` 和 `SRS-2` 可能需要保留版本区别。

如果不确定，`looks_same_concept` 填 `uncertain`。

---

## 模板字段说明

模板文件：

```text
alias_collection_template.csv
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| student_id | 是 | 你的编号，如 S01 |
| entity_name | 是 | 分配给你的实体名 |
| entity_type | 是 | 实体类型 |
| chinese_name | 否 | 中文名 |
| english_full_name | 否 | 英文全称 |
| abbreviation | 否 | 缩写 |
| aliases | 否 | 可能别名，用英文分号 ; 分隔 |
| version_or_variant | 否 | 是否版本/变体 |
| looks_same_concept | 是 | true / false / uncertain |
| source_note | 是 | 来源备注 |
| notes | 否 | 备注 |

---

## entity_type 可选值

常见类型：

```text
AssessmentTool
Intervention
Condition
Symptom
Comorbidity
Risk
AgeStage
Setting
Mechanism
Task
```

如果不知道类型，可以先填 `uncertain`，并在 notes 说明。

---

## looks_same_concept 怎么填

```text
true = 看起来是同一个概念
false = 看起来不是同一个概念，可能是不同版本或不同工具
uncertain = 不确定
```

注意：这里不是最终判断，只是你的候选意见。

---

## 合格示例

```csv
student_id,entity_name,entity_type,chinese_name,english_full_name,abbreviation,aliases,version_or_variant,looks_same_concept,source_note,notes
S01,ABA,Intervention,应用行为分析,Applied Behavior Analysis,ABA,ABA therapy;ABA训练法;应用行为分析训练,,true,干预综述,
S01,ADOS-2,AssessmentTool,孤独症诊断观察量表第二版,Autism Diagnostic Observation Schedule Second Edition,ADOS-2,ADOS Second Edition,version,false,评估工具文献,版本边界需保留
S01,M-CHAT-R/F,AssessmentTool,改良版婴幼儿孤独症筛查量表修订版及随访,Modified Checklist for Autism in Toddlers Revised with Follow-Up,M-CHAT-R/F,MCHAT-R/F;M-CHAT Revised with Follow-Up,version,uncertain,筛查工具文献,不确定是否应与 M-CHAT 合并
```

---

## 不合格示例

直接把不同版本写成完全相同：

```text
ADOS 和 ADOS-2 一样
```

更合适的写法：

```text
ADOS-2 是 ADOS 的第二版，可能需要保留版本边界。
```

来源备注太空：

```text
网上查的
```

更合适：

```text
来自某评估工具综述/文献标题/摘要
```

---

## 文件命名

完成后保存为：

```text
ALIAS_<student_id>_<name_pinyin>_result.csv
```

示例：

```text
ALIAS_S01_zhangsan_result.csv
```
