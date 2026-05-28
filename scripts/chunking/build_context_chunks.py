#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path

ZH_TITLE_KEYWORDS = {
    "摘要",
    "引言",
    "前言",
    "方法",
    "材料与方法",
    "结果",
    "讨论",
    "结论",
    "参考文献",
}
EN_TITLE_KEYWORDS = {
    "abstract",
    "introduction",
    "methods",
    "materials and methods",
    "results",
    "discussion",
    "conclusion",
    "references",
}


@dataclass
class Segment:
    page_id: int
    text: str
    heading_path: list[str]

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    punct = len(re.findall(r"[^\w\s]", text, flags=re.UNICODE))
    return max(1, int(cjk * 1.0 + words * 0.6 + punct * 0.2))


def normalize_line(line: str) -> str:
    line = line.replace("\u00a0", " ").replace("\t", " ").replace("\x00", "")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def parse_allow_doc_ids(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    allow: set[str] = set()
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = obj.get("doc_id")
            if doc_id:
                allow.add(doc_id)
    return allow


def parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y"}:
        return True
    if s in {"0", "false", "no", "n"}:
        return False
    return None


def parse_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_source_metadata(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}

    by_doc_id: dict[str, dict] = {}
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as rf:
            reader = csv.DictReader(rf)
            for row in reader:
                doc_id = (row.get("doc_id") or "").strip()
                if not doc_id:
                    continue
                row["year"] = parse_int(row.get("year"))
                row["include_flag"] = parse_bool(row.get("include_flag"))
                by_doc_id[doc_id] = row
        return by_doc_id

    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = row.get("doc_id")
            if not doc_id:
                continue
            row["year"] = parse_int(row.get("year"))
            row["include_flag"] = parse_bool(row.get("include_flag"))
            by_doc_id[doc_id] = row
    return by_doc_id


def extract_pages(obj: dict) -> list[dict]:
    clean = obj.get("clean", {})
    page_texts = clean.get("page_texts") or []
    if page_texts:
        out = []
        for i, p in enumerate(page_texts):
            out.append({"page_id": int(p.get("page_id", i + 1)), "text": p.get("text", "")})
        return out

    text = clean.get("text", "") or ""
    if not text.strip():
        return []

    out: list[dict] = []
    parts = re.split(r"\[PAGE\s+(\d+)\]", text)
    if len(parts) > 1:
        for i in range(1, len(parts), 2):
            pid = int(parts[i])
            body = parts[i + 1] if i + 1 < len(parts) else ""
            out.append({"page_id": pid, "text": body.strip()})
    else:
        out.append({"page_id": 1, "text": text.strip()})
    return out


def split_sentences(paragraph: str) -> list[str]:
    paragraph = paragraph.strip()
    if not paragraph:
        return []
    pieces = re.split(r"(?<=[。！？!?；;\.])\s+", paragraph)
    pieces = [p.strip() for p in pieces if p.strip()]
    if len(pieces) <= 1:
        pieces = re.split(r"(?<=[，,：:])\s+", paragraph)
        pieces = [p.strip() for p in pieces if p.strip()]
    return pieces if pieces else [paragraph]


def split_oversize_text(text: str, max_tokens: int) -> list[str]:
    if estimate_tokens(text) <= max_tokens:
        return [text]

    sents = split_sentences(text)
    if len(sents) <= 1:
        max_chars = max(320, int(max_tokens * 2.2))
        return [text[i : i + max_chars].strip() for i in range(0, len(text), max_chars) if text[i : i + max_chars].strip()]

    out: list[str] = []
    cur: list[str] = []
    cur_tok = 0
    for s in sents:
        st = estimate_tokens(s)
        if cur and cur_tok + st > max_tokens:
            out.append(" ".join(cur).strip())
            cur = [s]
            cur_tok = st
        else:
            cur.append(s)
            cur_tok += st
    if cur:
        out.append(" ".join(cur).strip())
    return out


def merge_wrapped_lines(lines: list[str]) -> list[str]:
    if not lines:
        return []
    out: list[str] = []
    cur = lines[0]
    hard_end = set("。！？!?；;.:：)]）】\"'”’")
    for ln in lines[1:]:
        is_h, _, _ = detect_heading(ln)
        if is_h:
            out.append(cur.strip())
            cur = ln
            continue

        # Merge probable wrapped lines from OCR/PDF text flow.
        if cur and cur[-1] not in hard_end and len(cur) < 180:
            cur = f"{cur} {ln}".strip()
        else:
            out.append(cur.strip())
            cur = ln
    if cur.strip():
        out.append(cur.strip())
    return [x for x in out if x]


def detect_heading(line: str) -> tuple[bool, int | None, str]:
    s = normalize_line(line)
    if not s or len(s) > 90:
        return (False, None, "")

    if s in ZH_TITLE_KEYWORDS or s.lower() in EN_TITLE_KEYWORDS:
        return (True, 1, s)

    if re.match(r"^第\s*[一二三四五六七八九十百千万0-9]+\s*[章节篇部分]", s):
        return (True, 1, s)

    m = re.match(r"^([0-9]+(?:\.[0-9]+){0,4})\s*[、\.．\)]?\s*\S+", s)
    if m:
        level = m.group(1).count(".") + 1
        return (True, min(5, level), s)

    if re.match(r"^[IVXLCM]+[\.\)]\s+\S+", s):
        return (True, 1, s)

    if re.match(r"^[A-Z][A-Z\s\-]{4,}$", s):
        return (True, 1, s)

    return (False, None, "")


def update_heading_path(path: list[str], heading: str, level: int | None) -> list[str]:
    if not heading:
        return path
    if level is None:
        return [heading] if not path else [path[0], heading]
    base = path[: max(0, level - 1)]
    return base + [heading]


def is_noise_segment(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if re.fullmatch(r"[\W_]+", t):
        return True
    if len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", t)) < 8 and len(t) < 36:
        return True
    return False


def split_page_to_segments(page_id: int, text: str, heading_path: list[str]) -> tuple[list[Segment], list[str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [normalize_line(x) for x in text.split("\n")]
    lines = [x for x in lines if x and not re.match(r"^\[PAGE\s+\d+\]$", x)]

    raw_parts = [p.strip() for p in re.split(r"\n\s*\n+", "\n".join(lines)) if p.strip()]
    if len(raw_parts) <= 1:
        raw_parts = merge_wrapped_lines(lines)

    out: list[Segment] = []
    path = heading_path[:]
    pending_headings: list[str] = []

    for part in raw_parts:
        is_h, level, heading = detect_heading(part)
        if is_h:
            path = update_heading_path(path, heading, level)
            pending_headings.append(heading)
            continue

        text_part = part
        if pending_headings:
            text_part = "\n".join(pending_headings + [text_part])
            pending_headings = []

        if is_noise_segment(text_part):
            continue

        for sp in split_oversize_text(text_part, max_tokens=600):
            if not is_noise_segment(sp):
                out.append(Segment(page_id=page_id, text=sp, heading_path=path[:]))

    if pending_headings:
        text_part = "\n".join(pending_headings)
        if not is_noise_segment(text_part):
            out.append(Segment(page_id=page_id, text=text_part, heading_path=path[:]))

    return out, path


def _build_chunk_record(
    doc_meta: dict,
    chunk_idx: int,
    segments: list[Segment],
) -> dict:
    text = "\n\n".join(s.text for s in segments).strip()
    pages = [s.page_id for s in segments]
    heading_path: list[str] = []
    for s in reversed(segments):
        if s.heading_path:
            heading_path = s.heading_path
            break

    return {
        "chunk_id": f"{doc_meta['doc_id']}_c{chunk_idx:04d}",
        "doc_id": doc_meta["doc_id"],
        "relative_path": doc_meta.get("relative_path"),
        "source_group": doc_meta.get("source_group"),
        "file_type": doc_meta.get("file_type"),
        "title": doc_meta.get("title"),
        "language": doc_meta.get("language"),
        "year": doc_meta.get("year"),
        "source_type": doc_meta.get("source_type"),
        "evidence_level": doc_meta.get("evidence_level"),
        "include_flag": doc_meta.get("include_flag"),
        "page_start": min(pages) if pages else 1,
        "page_end": max(pages) if pages else 1,
        "heading_path": heading_path,
        "text": text,
        "token_estimate": estimate_tokens(text),
        "char_count": len(text),
        "segment_count": len(segments),
        "prev_chunk_id": None,
        "next_chunk_id": None,
    }


def overlap_tail(segments: list[Segment], overlap_tokens: int) -> list[Segment]:
    if overlap_tokens <= 0:
        return []
    out: list[Segment] = []
    tok = 0
    for s in reversed(segments):
        st = s.tokens
        if tok >= overlap_tokens and out:
            break
        out.append(s)
        tok += st
    out.reverse()
    return out


def chunk_segments(
    doc_meta: dict,
    segments: list[Segment],
    target_tokens: int,
    overlap_tokens: int,
    min_tokens: int,
    max_tokens: int,
) -> list[dict]:
    chunks: list[dict] = []
    cur: list[Segment] = []
    cur_tokens = 0
    chunk_idx = 0

    def emit(buf: list[Segment]) -> None:
        nonlocal chunk_idx
        if not buf:
            return
        rec = _build_chunk_record(doc_meta, chunk_idx, buf)
        chunks.append(rec)
        chunk_idx += 1

    expanded: list[Segment] = []
    for s in segments:
        if s.tokens <= max_tokens:
            expanded.append(s)
            continue
        for piece in split_oversize_text(s.text, max_tokens=max_tokens):
            expanded.append(Segment(page_id=s.page_id, text=piece, heading_path=s.heading_path[:]))

    for s in expanded:
        st = s.tokens
        if cur and cur_tokens + st > target_tokens and cur_tokens >= min_tokens:
            emit(cur)
            cur = overlap_tail(cur, overlap_tokens)
            cur_tokens = sum(x.tokens for x in cur)

        cur.append(s)
        cur_tokens += st

        if cur_tokens > max_tokens and len(cur) > 1:
            emit(cur[:-1])
            cur = [cur[-1]]
            cur_tokens = cur[-1].tokens

    if cur:
        if chunks and cur_tokens < min_tokens:
            prev = chunks[-1]
            merged_text = prev["text"].strip() + "\n\n" + "\n\n".join(s.text for s in cur).strip()
            prev["text"] = merged_text.strip()
            prev["token_estimate"] = estimate_tokens(prev["text"])
            prev["char_count"] = len(prev["text"])
            prev["segment_count"] += len(cur)
            prev["page_end"] = max(prev["page_end"], max(s.page_id for s in cur))
        else:
            emit(cur)

    for i in range(len(chunks)):
        if i > 0:
            chunks[i]["prev_chunk_id"] = chunks[i - 1]["chunk_id"]
        if i < len(chunks) - 1:
            chunks[i]["next_chunk_id"] = chunks[i + 1]["chunk_id"]

    return chunks


def process_doc(
    obj: dict,
    source_meta: dict[str, dict],
    target_tokens: int,
    overlap_tokens: int,
    min_tokens: int,
    max_tokens: int,
) -> list[dict]:
    pages = extract_pages(obj)
    if not pages:
        return []

    path: list[str] = []
    segments: list[Segment] = []
    for p in pages:
        page_id = int(p.get("page_id", 1))
        text = p.get("text", "") or ""
        segs, path = split_page_to_segments(page_id, text, path)
        segments.extend(segs)

    if not segments:
        return []

    clean = obj.get("clean", {})
    doc_id = obj.get("doc_id")
    external_meta = source_meta.get(doc_id, {})
    meta = {
        "doc_id": doc_id,
        "relative_path": obj.get("relative_path"),
        "source_group": obj.get("source_group"),
        "file_type": obj.get("file_type"),
        "language": clean.get("language"),
        "title": external_meta.get("title"),
        "year": external_meta.get("year"),
        "source_type": external_meta.get("source_type"),
        "evidence_level": external_meta.get("evidence_level"),
        "include_flag": external_meta.get("include_flag"),
    }
    return chunk_segments(meta, segments, target_tokens, overlap_tokens, min_tokens, max_tokens)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build KGRAG context chunks from cleaned docs")
    ap.add_argument("--input", default="data/processed/cleaned_full")
    ap.add_argument("--allow-doc-ids", default="data/processed/cleaned_full/reports/clean_quality_keep_A_B.jsonl")
    ap.add_argument("--source-metadata", default="data/processed/source_catalog/source_metadata.jsonl")
    ap.add_argument("--output", default="data/processed/chunks_full")
    ap.add_argument("--target-tokens", type=int, default=520)
    ap.add_argument("--overlap-tokens", type=int, default=90)
    ap.add_argument("--min-tokens", type=int, default=180)
    ap.add_argument("--max-tokens", type=int, default=760)
    ap.add_argument("--limit-docs", type=int, default=0)
    args = ap.parse_args()

    in_root = Path(args.input).resolve()
    docs_dir = in_root / "docs"
    out_root = Path(args.output).resolve()
    out_reports = out_root / "reports"
    out_root.mkdir(parents=True, exist_ok=True)
    out_reports.mkdir(parents=True, exist_ok=True)

    allow_ids = parse_allow_doc_ids(Path(args.allow_doc_ids).resolve()) if args.allow_doc_ids else set()
    source_meta = load_source_metadata(Path(args.source_metadata).resolve()) if args.source_metadata else {}

    docs = sorted(docs_dir.glob("*.json"))
    if allow_ids:
        docs = [p for p in docs if p.stem in allow_ids]
    if args.limit_docs > 0:
        docs = docs[: args.limit_docs]

    if not docs:
        print("No cleaned docs found for chunking")
        return 1

    chunk_rows: list[dict] = []
    doc_map: dict[str, dict] = {}
    processed = 0

    for dp in docs:
        obj = json.loads(dp.read_text(encoding="utf-8"))
        rows = process_doc(
            obj=obj,
            source_meta=source_meta,
            target_tokens=args.target_tokens,
            overlap_tokens=args.overlap_tokens,
            min_tokens=args.min_tokens,
            max_tokens=args.max_tokens,
        )
        processed += 1
        doc_id = obj.get("doc_id")
        if rows:
            doc_map[doc_id] = {
                "doc_id": doc_id,
                "relative_path": obj.get("relative_path"),
                "source_group": obj.get("source_group"),
                "title": source_meta.get(doc_id, {}).get("title"),
                "year": source_meta.get(doc_id, {}).get("year"),
                "source_type": source_meta.get(doc_id, {}).get("source_type"),
                "evidence_level": source_meta.get(doc_id, {}).get("evidence_level"),
                "include_flag": source_meta.get(doc_id, {}).get("include_flag"),
                "chunk_count": len(rows),
                "chunk_ids": [r["chunk_id"] for r in rows],
            }
            chunk_rows.extend(rows)
        else:
            doc_map[doc_id] = {
                "doc_id": doc_id,
                "relative_path": obj.get("relative_path"),
                "source_group": obj.get("source_group"),
                "title": source_meta.get(doc_id, {}).get("title"),
                "year": source_meta.get(doc_id, {}).get("year"),
                "source_type": source_meta.get(doc_id, {}).get("source_type"),
                "evidence_level": source_meta.get(doc_id, {}).get("evidence_level"),
                "include_flag": source_meta.get(doc_id, {}).get("include_flag"),
                "chunk_count": 0,
                "chunk_ids": [],
            }

        if processed % 20 == 0 or processed == len(docs):
            print(f"[{processed}/{len(docs)}] chunks={len(chunk_rows)}")

    chunks_jsonl = out_root / "chunks.jsonl"
    chunks_jsonl.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in chunk_rows) + ("\n" if chunk_rows else ""),
        encoding="utf-8",
    )

    (out_root / "doc_chunk_map.json").write_text(
        json.dumps(doc_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tok = [r["token_estimate"] for r in chunk_rows] or [0]
    summary = {
        "docs_total": len(docs),
        "docs_with_chunks": sum(1 for v in doc_map.values() if v["chunk_count"] > 0),
        "chunks_total": len(chunk_rows),
        "chunks_per_doc": round(len(chunk_rows) / max(1, len(docs)), 2),
        "token_estimate": {
            "min": min(tok),
            "median": sorted(tok)[len(tok) // 2],
            "max": max(tok),
        },
        "params": {
            "target_tokens": args.target_tokens,
            "overlap_tokens": args.overlap_tokens,
            "min_tokens": args.min_tokens,
            "max_tokens": args.max_tokens,
        },
        "output": str(chunks_jsonl),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
