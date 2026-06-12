# CHUNKREVIEW：文献片段元数据复核任务

## 任务目标

请检查抽样文献片段是否存在明显问题，例如标题错误、年份错误、乱码、内容不相关或截断严重。

你不需要运行代码，也不需要查数据库。

---

## 每人工作量

建议每人审核：

```text
30-50 条文献片段
```

---

## 你会拿到什么

主力开发同学或任务协调同学会给你一个抽样文件，通常包含：

- `chunk_id`
- `title`
- `year`
- `evidence_level`
- `source_type`
- `text_preview`

你根据这些信息判断是否有明显问题。

---

## 检查项说明

### title_ok：标题是否正常

如果标题明显不是这段内容对应的文献，填 `false`。

不确定填 `uncertain`。

### year_ok：年份是否正常

如果年份明显缺失或不合理，填 `false`。

### readable：文本是否可读

如果出现严重乱码、排版破碎到无法阅读，填 `false`。

### asd_related：是否 ASD 相关

如果内容明显不是 ASD、孤独症、发育障碍、评估或干预相关，填 `false`。

### severe_truncation：是否严重截断

如果片段断得很严重，无法理解上下文，填 `true`。

---

## problem_type 可选值

```text
title_error
year_error
garbled_text
not_asd_related
severe_truncation
duplicate
other
```

如果没有明显问题，`problem_type` 留空。

---

## 模板字段说明

模板文件：

```text
chunk_metadata_review_template.csv
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| student_id | 是 | 你的编号，如 S01 |
| chunk_id | 是 | 文献片段编号 |
| title_ok | 是 | true / false / uncertain |
| year_ok | 是 | true / false / uncertain |
| readable | 是 | true / false / uncertain |
| asd_related | 是 | true / false / uncertain |
| severe_truncation | 是 | true / false / uncertain |
| problem_type | 否 | 问题类型 |
| notes | 否 | 备注 |

---

## 合格示例

```csv
student_id,chunk_id,title_ok,year_ok,readable,asd_related,severe_truncation,problem_type,notes
S01,abc_c0001,true,true,true,true,false,,无明显问题
S01,abc_c0002,false,true,true,true,false,title_error,标题似乎不是该文献
S01,abc_c0003,true,true,false,uncertain,true,garbled_text,文本乱码且截断严重
```

---

## 注意事项

如果你标记了某个问题，请尽量在 `notes` 里说明原因。

不确定就写 `uncertain`，不要猜。

---

## 文件命名

完成后保存为：

```text
CHUNKREVIEW_<student_id>_<name_pinyin>_result.csv
```

示例：

```text
CHUNKREVIEW_S01_zhangsan_result.csv
```
