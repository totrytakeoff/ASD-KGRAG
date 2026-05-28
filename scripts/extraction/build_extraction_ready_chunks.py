#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


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


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def is_noisy_chunk(text: str) -> bool:
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
    ap = argparse.ArgumentParser(description="Build a full-run extraction-ready chunk set")
    ap.add_argument("--input", default="data/processed/chunks_full/chunks.jsonl")
    ap.add_argument("--output", default="data/processed/chunks_extractable_full_ab_nonbook.jsonl")
    ap.add_argument("--min-evidence-levels", nargs="+", default=["A", "B"])
    ap.add_argument("--exclude-source-types", nargs="*", default=["book"])
    ap.add_argument("--drop-noisy", action="store_true", default=True)
    args = ap.parse_args()

    keep_levels = set(args.min_evidence_levels)
    exclude_types = set(args.exclude_source_types)

    selected = []
    summary = Counter()
    for row in iter_jsonl(Path(args.input)):
        summary["total"] += 1
        if row.get("evidence_level") not in keep_levels:
            summary["skip_evidence"] += 1
            continue
        if row.get("source_type") in exclude_types:
            summary["skip_source_type"] += 1
            continue
        text = row.get("text", "")
        if args.drop_noisy and is_noisy_chunk(text):
            summary["skip_noisy"] += 1
            continue
        selected.append(row)
        summary["selected"] += 1

    out_path = Path(args.output)
    out_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")

    print(json.dumps({
        "output": str(out_path),
        "selected": summary["selected"],
        "total": summary["total"],
        "skip_evidence": summary["skip_evidence"],
        "skip_source_type": summary["skip_source_type"],
        "skip_noisy": summary["skip_noisy"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
