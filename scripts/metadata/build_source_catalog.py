#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-3]\d)\b")


def clean_title(raw: str) -> str:
    title = Path(raw).stem
    title = re.sub(r"\s*-\s*PMC$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*（自闭症.*?）$", "", title)
    title = re.sub(r"\s*\(自闭症.*?\)$", "", title)
    title = re.sub(r"\s+", " ", title).strip(" _-")
    return title


def detect_year(relative_path: str, doc_payload: dict) -> int | None:
    text = (((doc_payload.get("clean") or {}).get("text")) or "")[:4000]
    title = clean_title(relative_path)
    candidates = YEAR_RE.findall(" ".join([relative_path, title, text]))
    years = [int(y) for y in candidates]
    if not years:
        return None
    return max(years)


def detect_source_type(source_group: str, title: str) -> str:
    text = f"{source_group} {title}".lower()
    if "相关书籍" in source_group:
        return "book"
    if any(k in text for k in ["guideline", "指南", "共识", "practice parameter", "recommendation", "statement"]):
        return "guideline_or_consensus"
    if any(k in text for k in ["meta-analysis", "meta analysis", "meta分析", "网状meta", "systematic review", "系统综述"]):
        return "systematic_review_or_meta"
    if any(k in text for k in ["review", "综述", "述评", "进展"]):
        return "narrative_review"
    if any(k in text for k in ["randomized", "随机", "trial", "对照试验", "rct"]):
        return "trial"
    if any(k in text for k in ["protocol", "方案", "研究设计"]):
        return "protocol"
    if any(k in text for k in ["个案", "case report", "病例"]):
        return "case_report"
    if any(k in text for k in ["蓝皮书", "手册", "指南"]):
        return "manual_or_report"
    return "article"


def detect_evidence_level(source_type: str, source_group: str, title: str) -> str:
    text = f"{source_group} {title}".lower()
    if source_type == "guideline_or_consensus":
        return "S"
    if source_type in {"systematic_review_or_meta", "trial"}:
        return "A"
    if source_type in {"narrative_review", "article", "manual_or_report"}:
        return "B"
    if source_type in {"case_report", "protocol"}:
        return "C"
    if source_type == "book":
        if any(k in text for k in ["家长", "parents", "100问", "希望你知道", "世界", "指南"]):
            return "C"
        return "B"
    return "B"


def detect_license(source_group: str, title: str) -> str:
    text = f"{source_group} {title}".lower()
    if "pmc" in text:
        return "public_web_open_access"
    if "相关书籍" in source_group:
        return "copyright_restricted"
    return "unknown"


def build_row(manifest_row: dict, docs_root: Path) -> dict:
    doc_id = manifest_row["doc_id"]
    relative_path = manifest_row["relative_path"]
    doc_path = docs_root / f"{doc_id}.json"
    payload = json.loads(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else {}

    title = clean_title(relative_path)
    source_group = manifest_row.get("source_group", "")
    source_type = detect_source_type(source_group, title)
    evidence_level = detect_evidence_level(source_type, source_group, title)

    return {
        "doc_id": doc_id,
        "relative_path": relative_path,
        "source_group": source_group,
        "title": title,
        "year": detect_year(relative_path, payload),
        "language": manifest_row.get("language") or ((payload.get("clean") or {}).get("language")),
        "source_type": source_type,
        "evidence_level": evidence_level,
        "include_flag": source_type != "protocol",
        "license": detect_license(source_group, title),
        "url": "",
        "notes": "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build source metadata catalog for ASD-KGRAG")
    ap.add_argument("--manifest", default="data/processed/cleaned_full/manifest.jsonl")
    ap.add_argument("--docs-root", default="data/processed/cleaned_full/docs")
    ap.add_argument("--output", default="data/processed/source_catalog")
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    docs_root = Path(args.docs_root).resolve()
    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with manifest_path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("status") != "ok":
                continue
            rows.append(build_row(row, docs_root))

    rows.sort(key=lambda x: x["relative_path"])

    jsonl_path = out_root / "source_metadata.jsonl"
    jsonl_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )

    csv_path = out_root / "source_metadata.csv"
    fieldnames = [
        "doc_id",
        "relative_path",
        "source_group",
        "title",
        "year",
        "language",
        "source_type",
        "evidence_level",
        "include_flag",
        "license",
        "url",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as wf:
        writer = csv.DictWriter(wf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "total_docs": len(rows),
        "source_group_distribution": dict(Counter(r["source_group"] for r in rows)),
        "source_type_distribution": dict(Counter(r["source_type"] for r in rows)),
        "evidence_level_distribution": dict(Counter(r["evidence_level"] for r in rows)),
        "missing_year_count": sum(1 for r in rows if not r["year"]),
        "output_jsonl": str(jsonl_path),
        "output_csv": str(csv_path),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
