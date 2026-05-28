# 数据提取依赖清单

## 1) 当前主流程（已验证可用）

当前提取链使用以下脚本：
- `scripts/extraction/extract_raw_corpus.py`
- `scripts/extraction/assess_extraction_quality.py`
- `scripts/extraction/build_context_chunks.py`

Python 依赖：
- 无第三方 Python 包强依赖（仅标准库）

系统依赖（必需）：
- `poppler` 工具链：
  - `pdftotext`
  - `pdfinfo`
  - `pdfimages`
  - `pdftoppm`
- `tesseract` OCR：
  - `tesseract`
  - `tesseract-data-eng`
  - `tesseract-data-chi_sim`
  - `tesseract-data-chi_tra`
  - `tesseract-data-osd`

系统依赖（建议）：
- `unpaper`（预处理扫描页，后续可接入）

## 2) Arch Linux 安装命令

```bash
echo 'myself' | sudo -S pacman -Sy --needed \
  poppler tesseract tesseract-data-eng tesseract-data-chi_sim \
  tesseract-data-chi_tra tesseract-data-osd unpaper
```

说明：`poppler` 提供 `pdftotext/pdfinfo/pdfimages/pdftoppm`。

脚本目录内同步依赖文件：
- `scripts/extraction/requirements_extraction_system.txt`

## 3) 可选增强依赖（当前未作为主流程）

- `marker-pdf`（开源 PDF 提取增强方案）
- 视觉模型 API（图片语义补充）

说明：`marker-pdf` 在当前 `Python 3.14` 环境存在安装兼容风险（`Pillow<11` 构建失败风险较高），建议在隔离环境（如 Python 3.11/3.12 + docker）单独部署后再接入对比。
