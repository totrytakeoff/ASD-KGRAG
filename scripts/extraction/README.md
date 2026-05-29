# Extraction Scripts（详细说明）

## 1) `extract_raw_corpus.py`

作用：对 `PDF/DOCX` 执行原始提取，输出页级文本、OCR结果、图片统计与最终合并文本。

### 参数

- `--input`：输入目录（默认 `data/raw`）
- `--output`：输出目录（默认 `data/processed/extract_raw`）
- `--workers`：并行线程数
- `--limit`：只处理前 N 个文件（调试用）
- `--path-filter`：按相对路径正则筛选
- `--list-file`：按相对路径清单筛选（每行一个）
- `--ocr-mode`：`off|auto|always`
- `--ocr-threshold-cpp`：`auto` 模式触发 OCR 的字符/页阈值
- `--ocr-dpi`：OCR 转图 DPI
- `--ocr-max-pages`：每文档 OCR 最大页数（0=全页）
- `--ocr-lang`：OCR 语言包（默认 `chi_sim+eng`）

### 输出

- `docs/{doc_id}.json`
- `manifest.jsonl`
- `summary.json`

### 关键字段

- `extract.textlayer.page_texts`
- `extract.ocr.page_texts`
- `extract.merged.page_texts`
- `extract.merged.selected_source`
- `extract.merged.extraction_coverage_ratio`

## 2) `assess_extraction_quality.py`

作用：对提取结果做自动打分和抽样。

### 参数

- `--input`：提取结果目录
- `--sample-size`：抽样数量
- `--seed`：随机种子

### 输出

- `reports/quality_summary.json`
- `reports/quality_scored.jsonl`
- `reports/quality_samples.json`
- `reports/quality_lowest30.json`

## 3) `extract_entities_relations.py`

作用：从 `chunks.jsonl` 抽取实体、关系和证据元数据，输出 KGRAG 建图前的 JSONL。

### 参数

- `--input`：chunk 输入文件（默认 `data/processed/chunks_full/chunks.jsonl`）
- `--output`：抽取输出目录（默认 `data/processed/extraction_full`）
- `--schema`：抽取 schema JSON
- `--system-prompt`：抽取 system prompt
- `--backend`：`stub|openai`
- `--model`：模型名；不传时读取 `LLM_MODEL`
- `--base-url`：兼容 OpenAI API 的基础地址，如 `https://openrouter.ai/api/v1`
- `--api-key`：API key
- `--site-url`：可选，请求来源站点，OpenRouter 推荐传
- `--app-name`：可选，请求应用名
- `--max-tokens`：可选，限制模型输出 token；默认读取 `LLM_MAX_TOKENS`，未设置则不传
- `--response-format`：`json_object|none`；默认 `json_object`，兼容接口不稳定时可设为 `none`
- `--limit`：仅处理前 N 个 chunk（调试用）

### 输出

- `chunk_extractions.jsonl`
- `summary.json`

### 说明

- `stub` 模式用于先验证全链路和数据结构，不调用模型。
- `openai` backend 现已兼容通用 OpenAI-style API，不限于 OpenAI。
- 可通过命令行或环境变量提供配置：
  - `--base-url` / `LLM_BASE_URL`
  - `--api-key` / `LLM_API_KEY`
  - `--model` / `LLM_MODEL`
  - `--max-tokens` / `LLM_MAX_TOKENS`
  - `--response-format` / `LLM_RESPONSE_FORMAT`
  - 兼容读取 `OPENROUTER_API_KEY`、`OPENAI_API_KEY`
- 模型返回 ```json 代码块或前后带少量说明文本时，脚本会尝试从响应中提取 JSON 对象。

### OpenRouter 示例

```bash
export LLM_BASE_URL="https://openrouter.ai/api/v1"
export LLM_API_KEY="你的_openrouter_key"
export LLM_MODEL="deepseek-ai/DeepSeek-V4-Flash"

python scripts/extraction/extract_entities_relations.py \
  --backend openai \
  --site-url https://localhost \
  --app-name ASD-KGRAG \
  --input data/processed/chunks_full/chunks.jsonl \
  --output data/processed/extraction_pilot \
  --limit 100
```

### 批量抽取推荐入口

继续主干抽取：

```bash
MODE=throughput bash scripts/extraction/run_next_extraction_batch.sh
```

`MODE=throughput` 默认使用轻量 prompt 和输出上限：

- `SYSTEM_PROMPT=scripts/extraction/entity_relation_system_prompt_v6_light.txt`
- `MAX_TOKENS=1200`
- `REQUEST_TIMEOUT=60`
- `MAX_RETRIES=0`

接口状态较好、需要更稳健输出时：

```bash
MODE=balanced bash scripts/extraction/run_next_extraction_batch.sh
```

`MODE=balanced` 默认保留原 prompt，不限制输出 token，并使用更长请求超时与重试。

## 4) `normalize_extractions.py`

作用：将 chunk 级抽取结果做实体归一化、关系聚合，并生成 `entity_canonical_map.json`。

### 输出

- `entities.jsonl`
- `relations.jsonl`
- `evidence.jsonl`
- `entity_canonical_map.json`
- `summary.json`

## 5) `build_relation_rich_pilot.py`

作用：构造更适合评估实体/关系抽取质量的 pilot chunk 集，尽量避开表格、附录、参考文献型 chunk。

### 输出

- 一个筛选后的 `jsonl` pilot 文件

## 6) `build_context_chunks.py`

作用：将页级文本切分为 KGRAG 可用 chunk（保留页码和标题路径）。

### 参数

- `--input`：提取结果目录
- `--output`：chunk 输出目录
- `--target-tokens`：目标 chunk 大小
- `--overlap-tokens`：chunk 重叠大小

### 输出

- `chunks.jsonl`
- `summary.json`

## 7) 依赖

- 见：`requirements_extraction_system.txt`
