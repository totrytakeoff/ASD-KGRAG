#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def rough_tokens(s: str) -> int:
    # language-agnostic rough token estimator
    return max(1, int(len(s) / 2.7))


def split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    return parts


def heading_of(par: str) -> str | None:
    p = par.strip()
    if len(p) > 80:
        return None
    if re.match(r"^(第\s*[一二三四五六七八九十0-9]+\s*[章节]|[0-9]+(\.[0-9]+)*\s+)", p):
        return p
    return None


def chunk_page_text(page_text: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    paras = split_paragraphs(page_text)
    out: list[str] = []
    cur: list[str] = []
    cur_tok = 0

    for p in paras:
        t = rough_tokens(p)
        if cur and cur_tok + t > target_tokens:
            out.append("\n\n".join(cur))
            # overlap by tail paragraphs
            tail: list[str] = []
            tail_tok = 0
            for back in reversed(cur):
                bt = rough_tokens(back)
                if tail_tok + bt > overlap_tokens:
                    break
                tail.append(back)
                tail_tok += bt
            tail.reverse()
            cur = tail + [p]
            cur_tok = sum(rough_tokens(x) for x in cur)
        else:
            cur.append(p)
            cur_tok += t

    if cur:
        out.append("\n\n".join(cur))
    return [x for x in out if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build KGRAG context chunks from extracted docs")
    ap.add_argument("--input", default="data/processed/extract_raw_full")
    ap.add_argument("--output", default="data/processed/context_chunks")
    ap.add_argument("--target-tokens", type=int, default=600)
    ap.add_argument("--overlap-tokens", type=int, default=80)
    args = ap.parse_args()

    in_root = Path(args.input).resolve()
    docs_dir = in_root / "docs"
    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_root / "chunks.jsonl"

    docs = sorted(docs_dir.glob("*.json"))
    if not docs:
        print("No extracted docs found")
        return 1

    total = 0
    with out_jsonl.open("w", encoding="utf-8") as wf:
        for dp in docs:
            obj = json.loads(dp.read_text(encoding="utf-8"))
            merged = obj.get("extract", {}).get("merged", {})
            page_texts = merged.get("page_texts") or []
            if not page_texts:
                txt = merged.get("text", "")
                if txt.strip():
                    page_texts = [{"page_id": 1, "text": txt}]

            heading_stack: list[str] = []
            local_idx = 0
            for pg in page_texts:
                page_id = pg.get("page_id", 1)
                chunks = chunk_page_text(pg.get("text", ""), args.target_tokens, args.overlap_tokens)
                for c in chunks:
                    for par in split_paragraphs(c)[:2]:
                        h = heading_of(par)
                        if h:
                            heading_stack = [h]
                            break
                    cid = f"{obj['doc_id']}_p{int(page_id):04d}_c{local_idx:04d}"
                    local_idx += 1
                    rec = {
                        "chunk_id": cid,
                        "doc_id": obj["doc_id"],
                        "relative_path": obj.get("relative_path"),
                        "source_group": obj.get("source_group"),
                        "file_type": obj.get("file_type"),
                        "engine": "local_ocr",
                        "page_start": int(page_id),
                        "page_end": int(page_id),
                        "heading_path": heading_stack[:],
                        "text": c,
                        "token_estimate": rough_tokens(c),
                    }
                    wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total += 1

    summary = {
        "docs": len(docs),
        "chunks": total,
        "output": str(out_jsonl),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
