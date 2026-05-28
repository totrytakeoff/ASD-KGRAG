#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

GATE = {
    "min_doc_coverage": 0.99,
    "min_in_range_ratio": 0.95,
    "max_noisy_ratio": 0.03,
    "max_short_ratio": 0.03,
    "max_duplicate_ratio": 0.08,
}


def load_expected_doc_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    out: set[str] = set()
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            did = obj.get("doc_id")
            if did:
                out.add(did)
    return out


def normalized_signature(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"[\u3000\s]+", "", t)
    return t


def score_chunk(obj: dict, min_tokens: int, max_tokens: int) -> dict:
    text = obj.get("text", "") or ""
    tokens = int(obj.get("token_estimate") or 0)
    chars = len(text)

    weird_ratio = len(re.findall(r"[�□■◆▲▼※¤§]", text)) / max(chars, 1)
    alpha_num_cjk = len(re.findall(r"[A-Za-z0-9Ａ-Ｚａ-ｚ０-９\u4e00-\u9fff]", text))
    readable_ratio = alpha_num_cjk / max(chars, 1)

    risk: list[str] = []
    if tokens < 60:
        risk.append("too_short_severe")
    elif tokens < min_tokens:
        risk.append("too_short")
    if tokens > max_tokens + 250:
        risk.append("too_long_severe")
    elif tokens > max_tokens:
        risk.append("too_long")
    if weird_ratio > 0.02 or readable_ratio < 0.45:
        risk.append("noisy_high")
    elif weird_ratio > 0.01:
        risk.append("noisy_mild")

    if "too_short_severe" in risk or "noisy_high" in risk:
        grade = "D"
    elif "too_long_severe" in risk:
        grade = "D"
    elif "too_short" in risk or "too_long" in risk or "noisy_mild" in risk:
        grade = "C"
    else:
        grade = "A" if min_tokens <= tokens <= max_tokens else "B"

    return {
        "chunk_id": obj.get("chunk_id"),
        "doc_id": obj.get("doc_id"),
        "relative_path": obj.get("relative_path"),
        "page_start": obj.get("page_start"),
        "page_end": obj.get("page_end"),
        "token_estimate": tokens,
        "char_count": chars,
        "grade": grade,
        "risk_flags": sorted(set(risk)),
        "signature": normalized_signature(text),
    }


def choose_samples(rows: list[dict], n: int, seed: int) -> list[dict]:
    random.seed(seed)
    by_grade: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_grade[r["grade"]].append(r)

    out: list[dict] = []
    for g in ["D", "C", "B", "A"]:
        pool = by_grade.get(g, [])
        if not pool:
            continue
        k = min(max(1, n // 8), len(pool)) if g in {"D", "C"} else min(max(1, n // 16), len(pool))
        out.extend(random.sample(pool, k))

    if len(out) < n:
        rest = [r for r in rows if r not in out]
        out.extend(random.sample(rest, min(n - len(out), len(rest))))

    out = out[:n]
    rank = {"D": 0, "C": 1, "B": 2, "A": 3}
    out.sort(key=lambda x: (rank.get(x["grade"], 9), x["token_estimate"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Assess chunk quality for KGRAG")
    ap.add_argument("--input", default="data/processed/chunks_full")
    ap.add_argument("--expected-doc-ids", default="data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl")
    ap.add_argument("--min-tokens", type=int, default=180)
    ap.add_argument("--max-tokens", type=int, default=760)
    ap.add_argument("--short-threshold", type=int, default=120)
    ap.add_argument("--sample-size", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    root = Path(args.input).resolve()
    chunks_file = root / "chunks.jsonl"
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    if not chunks_file.exists():
        print(f"Chunk file not found: {chunks_file}")
        return 1

    rows = [json.loads(x) for x in chunks_file.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print("No chunks found")
        return 1

    scored = [score_chunk(x, args.min_tokens, args.max_tokens) for x in rows]
    grade_dist = Counter(r["grade"] for r in scored)

    tokens = [r["token_estimate"] for r in scored]
    short_ratio = sum(1 for t in tokens if t < args.short_threshold) / len(tokens)
    in_range_ratio = sum(1 for t in tokens if args.min_tokens <= t <= args.max_tokens) / len(tokens)
    long_ratio = sum(1 for t in tokens if t > args.max_tokens) / len(tokens)

    noisy_ratio = sum(1 for r in scored if "noisy_high" in r["risk_flags"] or "noisy_mild" in r["risk_flags"]) / len(scored)

    sig_count = Counter(r["signature"] for r in scored)
    dup_chunks = sum(v - 1 for v in sig_count.values() if v > 1)
    duplicate_ratio = dup_chunks / len(scored)

    docs_with_chunks = {r["doc_id"] for r in scored if r.get("doc_id")}
    expected_ids = load_expected_doc_ids(Path(args.expected_doc_ids).resolve()) if args.expected_doc_ids else set()
    if expected_ids:
        doc_coverage = len(docs_with_chunks & expected_ids) / max(1, len(expected_ids))
    else:
        doc_coverage = 1.0

    rank = {"D": 0, "C": 1, "B": 2, "A": 3}
    low = sorted(scored, key=lambda x: (rank.get(x["grade"], 9), x["token_estimate"]))[:40]
    samples = choose_samples(scored, args.sample_size, args.seed)
    keep_ab = [r for r in scored if r["grade"] in {"A", "B"}]
    review_cd = [r for r in scored if r["grade"] in {"C", "D", "F"}]
    review_docs = sorted({r["doc_id"] for r in review_cd if r.get("doc_id")})

    summary = {
        "total_chunks": len(scored),
        "docs_with_chunks": len(docs_with_chunks),
        "expected_docs": len(expected_ids),
        "doc_coverage": round(doc_coverage, 4),
        "grade_distribution": dict(grade_dist),
        "token_estimate": {
            "min": min(tokens),
            "median": round(median(tokens), 2),
            "max": max(tokens),
            "in_range_ratio": round(in_range_ratio, 4),
            "short_ratio": round(short_ratio, 4),
            "long_ratio": round(long_ratio, 4),
        },
        "noisy_ratio": round(noisy_ratio, 4),
        "duplicate_ratio": round(duplicate_ratio, 4),
        "quality_gate": {
            "thresholds": GATE,
            "actual": {
                "doc_coverage": round(doc_coverage, 4),
                "in_range_ratio": round(in_range_ratio, 4),
                "noisy_ratio": round(noisy_ratio, 4),
                "short_ratio": round(short_ratio, 4),
                "duplicate_ratio": round(duplicate_ratio, 4),
            },
            "passed": (
                doc_coverage >= GATE["min_doc_coverage"]
                and in_range_ratio >= GATE["min_in_range_ratio"]
                and noisy_ratio <= GATE["max_noisy_ratio"]
                and short_ratio <= GATE["max_short_ratio"]
                and duplicate_ratio <= GATE["max_duplicate_ratio"]
            ),
        },
        "for_kgrag": {
            "keep_chunks_A_B": len(keep_ab),
            "review_chunks_C_or_lower": len(review_cd),
            "review_doc_count": len(review_docs),
        },
    }

    (reports / "chunk_quality_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports / "chunk_quality_scored.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in r.items() if k != "signature"}, ensure_ascii=False) for r in scored) + "\n",
        encoding="utf-8",
    )
    (reports / "chunk_quality_samples.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "signature"} for r in samples], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (reports / "chunk_quality_lowest40.json").write_text(
        json.dumps([{k: v for k, v in r.items() if k != "signature"} for r in low], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (reports / "chunk_quality_keep_A_B.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in r.items() if k != "signature"}, ensure_ascii=False) for r in keep_ab) + "\n",
        encoding="utf-8",
    )
    (reports / "chunk_quality_review_C_or_lower.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in r.items() if k != "signature"}, ensure_ascii=False) for r in review_cd) + "\n",
        encoding="utf-8",
    )
    (reports / "chunk_review_doc_ids.txt").write_text(
        "\n".join(review_docs) + ("\n" if review_docs else ""),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"samples: {reports / 'chunk_quality_samples.json'}")
    print(f"lowest:  {reports / 'chunk_quality_lowest40.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
