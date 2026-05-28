#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TOOL_KEYWORDS = [
    "EEG",
    "ERP",
    "fMRI",
    "MEG",
    "MRI",
    "PET",
    "SPECT",
    "ADOS",
    "ADI-R",
    "M-CHAT",
    "量表",
    "筛查",
    "评估",
]

STUDY_TRIGGERS = [
    "研究表明",
    "研究发现",
    "结果显示",
    "显示",
    "发现",
    "通过",
    "使用",
    "采用",
    "showed",
    "found",
    "using",
    "assessed",
    "measured",
]

NOISY_MARKERS = [
    "附录",
    "表1",
    "表2",
    "表3",
    "参考文献",
    "关键词",
    "classification accuracy",
    "纳入分析被试的基本信息",
    "简要总结",
]


def score_chunk(obj: dict) -> tuple[int, int]:
    text = obj.get("text", "")
    score = sum(text.count(k) for k in TOOL_KEYWORDS) + 2 * sum(text.count(k) for k in STUDY_TRIGGERS)
    penalty = sum(text.count(k) for k in NOISY_MARKERS)
    return score, penalty


def is_noisy_chunk(obj: dict) -> bool:
    text = obj.get("text", "")
    if any(marker in text for marker in NOISY_MARKERS):
        return True
    if text.count(";") + text.count("；") > 12:
        return True
    if len(re.findall(r"\b[A-Z]{2,}[A-Z0-9\-]*\b", text)) > 40:
        return True
    if text.count("\n") > 35 and text.count("。") + text.count(".") < 8:
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a curated relation-rich pilot set")
    ap.add_argument("--input", default="data/processed/chunks_full/chunks.jsonl")
    ap.add_argument("--output", default="data/processed/chunks_pilot_rich_curated12.jsonl")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--max-per-doc", type=int, default=3)
    args = ap.parse_args()

    rows = []
    with Path(args.input).open("r", encoding="utf-8") as rf:
        for line in rf:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("source_type") == "book":
                continue
            score, penalty = score_chunk(obj)
            if score < 4:
                continue
            if is_noisy_chunk(obj):
                continue
            rows.append((score, -penalty, -obj.get("token_estimate", 0), obj))

    rows.sort(key=lambda item: (item[0], item[1], item[2], item[3]["chunk_id"]), reverse=True)
    selected = []
    doc_counts: dict[str, int] = {}
    for _, _, _, obj in rows:
        count = doc_counts.get(obj["doc_id"], 0)
        if count >= args.max_per_doc:
            continue
        selected.append(obj)
        doc_counts[obj["doc_id"]] = count + 1
        if len(selected) >= args.limit:
            break

    out_path = Path(args.output)
    out_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    print(f"selected={len(selected)} output={out_path}")
    for row in selected:
        print(row["chunk_id"], row.get("title"), row.get("token_estimate"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
