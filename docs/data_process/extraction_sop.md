# 数据提取流程SOP（详细版）

本SOP用于把 `data/raw` 中的原始资料提取为可用于 KGRAG 的结构化数据，并可重复执行。

## 0. 目标与原则

- 目标：产出 `data/processed/extract_raw_full`，并保证可追溯、可评估、可迭代。
- 原则：
  - 先全量提取，再定向增强，不直接在原始文档上做破坏性处理。
  - 每一步都有输入、命令、输出、验收门槛。
  - 必须保留页级上下文（`page_texts/page_id`）供后续实体抽取与证据引用。

## 1. 目录约定

- 原始数据：`data/raw`
- 最终提取结果：`data/processed/extract_raw_full`
- 质量报告：`data/processed/extract_raw_full/reports`
- 脚本目录：`scripts/extraction`

## 2. 环境准备

### 2.1 系统依赖安装（Arch）

```bash
echo 'myself' | sudo -S pacman -Sy --needed \
  poppler tesseract tesseract-data-eng tesseract-data-chi_sim \
  tesseract-data-chi_tra tesseract-data-osd unpaper
```

### 2.2 依赖检查

```bash
command -v pdftotext pdfinfo pdfimages pdftoppm tesseract
```

验收标准：以上命令都能返回路径。

## 3. 第一步：全量基础提取（不启用OCR）

### 输入

- `data/raw`

### 命令

```bash
python scripts/extraction/extract_raw_corpus.py \
  --input data/raw \
  --output data/processed/extract_raw_full \
  --workers 8 \
  --ocr-mode off
```

### 输出

- `data/processed/extract_raw_full/docs/*.json`
- `data/processed/extract_raw_full/manifest.jsonl`
- `data/processed/extract_raw_full/summary.json`

### 验收

- `summary.json` 中 `total == ok`。

## 4. 第二步：质量评估

### 命令

```bash
python scripts/extraction/assess_extraction_quality.py \
  --input data/processed/extract_raw_full \
  --sample-size 30 \
  --seed 42
```

### 输出

- `reports/quality_summary.json`
- `reports/quality_scored.jsonl`
- `reports/quality_samples.json`
- `reports/quality_lowest30.json`

### 关键指标解释

- `A/B/C/D/F`：文档提取质量等级。
- `pass_rate_B_or_above`：高质量通过率。
- `pass_rate_C_or_above`：可用率。
- `partial_coverage`：页覆盖不足，通常是 OCR 只跑了部分页。

### 建议门槛

- `pass_rate_C_or_above >= 0.95`
- `F == 0` 或接近 0

## 5. 第三步：筛选低质量文档，生成OCR重跑清单

### 命令

```bash
python - <<'PY'
import json
from pathlib import Path
scored=Path('data/processed/extract_raw_full/reports/quality_scored.jsonl')
rows=[json.loads(x) for x in scored.read_text(encoding='utf-8').splitlines() if x.strip()]
selected=[]
for r in rows:
    flags=set(r.get('flags',[]))
    if r['grade'] in {'F','D'} or 'anna_archive_marker' in flags or 'too_short' in flags:
        selected.append(r['relative_path'])
out=Path('data/processed/extract_raw_full/reports/ocr_rerun_list.txt')
out.write_text('\n'.join(sorted(set(selected)))+'\n',encoding='utf-8')
print('selected',len(set(selected)))
print('list',out)
PY
```

### 输出

- `reports/ocr_rerun_list.txt`

## 6. 第四步：定向OCR重提取（只跑清单）

### 命令（推荐快速版本）

```bash
python scripts/extraction/extract_raw_corpus.py \
  --input data/raw \
  --output data/processed/extract_raw_rerun_ocr \
  --workers 4 \
  --list-file data/processed/extract_raw_full/reports/ocr_rerun_list.txt \
  --ocr-mode always \
  --ocr-dpi 170 \
  --ocr-max-pages 5 \
  --ocr-lang chi_sim+eng
```

### 输出

- `data/processed/extract_raw_rerun_ocr/docs/*.json`

### 参数调优策略

- `--ocr-max-pages`：优先 5/12，必要时再上 30。
- `--ocr-dpi`：优先 170~200，过高会显著增时。

## 7. 第五步：回填合并OCR结果到最终集

### 命令

```bash
python - <<'PY'
import json, shutil
from pathlib import Path
full=Path('data/processed/extract_raw_full')
rer=Path('data/processed/extract_raw_rerun_ocr')
for p in (rer/'docs').glob('*.json'):
    shutil.copy2(p, (full/'docs'/p.name))
# rebuild manifest + summary
rows=[]
for p in sorted((full/'docs').glob('*.json')):
    o=json.loads(p.read_text(encoding='utf-8'))
    m=o.get('extract',{}).get('merged',{})
    rows.append({
      'doc_id':o.get('doc_id'),'relative_path':o.get('relative_path'),
      'source_group':o.get('source_group'),'file_type':o.get('file_type'),
      'status':o.get('status','ok'),'error':o.get('error'),'chars':m.get('chars',0),
      'language':m.get('language','unknown'),'chars_per_page':m.get('chars_per_page'),
      'selected_source':m.get('selected_source'),
      'ocr_attempted':bool(o.get('extract',{}).get('ocr',{}).get('attempted',False)),
      'ocr_chars':int(o.get('extract',{}).get('ocr',{}).get('chars',0) or 0),
    })
(full/'manifest.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n',encoding='utf-8')
summary={
  'total':len(rows),'ok':sum(1 for r in rows if r['status']=='ok'),'error':sum(1 for r in rows if r['status']!='ok'),
  'ocr_mode':'mixed(textlayer+targeted_ocr)','ocr_available':True,
  'ocr_attempted_docs':sum(1 for r in rows if r['ocr_attempted']),
  'ocr_selected_docs':sum(1 for r in rows if r.get('selected_source')=='ocr'),
}
(full/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
PY
```

## 8. 第六步：最终质量复评

### 命令

```bash
python scripts/extraction/assess_extraction_quality.py \
  --input data/processed/extract_raw_full \
  --sample-size 30 \
  --seed 42
```

### 最终验收门槛（建议）

- `pass_rate_C_or_above >= 0.98`
- `F == 0`
- `summary.total == manifest行数`

## 9. 第七步：构建KGRAG上下文chunks

### 命令

```bash
python scripts/extraction/build_context_chunks.py \
  --input data/processed/extract_raw_full \
  --output data/processed/context_chunks \
  --target-tokens 600 \
  --overlap-tokens 80
```

### 输出

- `data/processed/context_chunks/chunks.jsonl`
- `data/processed/context_chunks/summary.json`

### 对下游抽取的价值

- 每个 chunk 保留：`doc_id/page_start/page_end/heading_path`。
- 便于实体关系抽取时回溯证据与上下文窗口。

## 10. 常见问题与处理

- OCR非常慢：降低 `--ocr-max-pages`、降低 `--ocr-dpi`、减少 `--workers`。
- 文本仍是目录/元数据：提高 OCR 页数，并在清洗阶段加入目录页降权/剔除规则。
- marker-pdf 安装失败：当前环境 Python 3.14 与 `Pillow<11` 兼容性差，建议在 `Python 3.11/3.12` 隔离环境部署。
