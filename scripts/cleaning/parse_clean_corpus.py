#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

SUPPORTED_SUFFIXES = {".pdf", ".docx"}
PUNCT_END = set("。！？.!?:：;；)]）】\"'")


@dataclass
class ParsedDoc:
    source_path: str
    relative_path: str
    doc_id: str
    source_group: str
    file_type: str
    language: str
    text_raw_len: int
    text_clean_len: int
    line_count_clean: int
    removed_references: bool
    status: str
    error: Optional[str] = None


def sha1_short(value: str, n: int = 16) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:n]


def detect_language(text: str) -> str:
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    if zh == 0 and en == 0:
        return "unknown"
    if zh >= en:
        return "zh"
    return "en"


def iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            yield p


def extract_pdf_text(path: Path) -> str:
    # Try plain extraction first, fallback to layout mode if output is too short.
    cmds = [
        ["pdftotext", "-enc", "UTF-8", "-nopgbrk", str(path), "-"],
        ["pdftotext", "-enc", "UTF-8", "-nopgbrk", "-layout", str(path), "-"],
    ]
    last_err = ""
    for cmd in cmds:
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True)
            if proc.returncode != 0:
                last_err = proc.stderr.decode("utf-8", errors="ignore").strip()
                continue
            text = proc.stdout.decode("utf-8", errors="ignore")
            if len(text.strip()) >= 80:
                return text
            # accept short text on second fallback
            if cmd is cmds[-1]:
                return text
        except Exception as exc:  # pragma: no cover
            last_err = str(exc)
    raise RuntimeError(last_err or "pdftotext failed")


def extract_docx_text(path: Path) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
    except (BadZipFile, KeyError) as exc:
        raise RuntimeError(f"docx open failed: {exc}") from exc

    root = ET.fromstring(xml)
    lines: list[str] = []
    for p in root.findall(".//w:p", ns):
        pieces: list[str] = []
        for t in p.findall(".//w:t", ns):
            if t.text:
                pieces.append(t.text)
        line = "".join(pieces).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def normalize_line(line: str) -> str:
    line = line.replace("\u00a0", " ").replace("\t", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def trim_references(lines: list[str]) -> tuple[list[str], bool]:
    # Trim trailing reference sections; keeps body text for downstream extraction.
    markers = [
        re.compile(r"^(参考文献|参\s*考\s*文\s*献)\s*$", re.IGNORECASE),
        re.compile(r"^(references|bibliography)\b", re.IGNORECASE),
    ]
    for idx, line in enumerate(lines):
        low = line.lower()
        if len(line) <= 40 and any(m.search(low) for m in markers):
            return lines[:idx], True
    return lines, False


def join_wrapped_lines(lines: list[str]) -> str:
    # Merge hard-wrapped lines while preserving paragraph boundaries.
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if not cur:
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue

        merged = cur
        j = i + 1
        while j < len(lines) and lines[j]:
            nxt = lines[j]
            if (
                merged
                and merged[-1] not in PUNCT_END
                and not re.match(r"^([\-•·\d]+[\).、．\.]?\s+)", nxt)
                and len(merged) < 280
            ):
                merged += " " + nxt
                j += 1
            else:
                break
        out.append(merged)
        i = j

    # Collapse multiple blank lines
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(raw: str) -> tuple[str, bool]:
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"([A-Za-z])-\n([A-Za-z])", r"\1\2", text)

    raw_lines = text.split("\n")
    lines = [normalize_line(x) for x in raw_lines]

    # Remove obvious page numbers and low-information artifacts.
    cleaned: list[str] = []
    for ln in lines:
        if not ln:
            cleaned.append("")
            continue
        if re.fullmatch(r"\d{1,4}", ln):
            continue
        if re.fullmatch(r"第\s*\d+\s*页", ln):
            continue
        if len(ln) <= 1 and ln not in {"。", "."}:
            continue
        cleaned.append(ln)

    # Remove globally repeated short headers/footers.
    c = Counter([x for x in cleaned if 0 < len(x) <= 40])
    repeated = {k for k, v in c.items() if v >= 8}
    filtered = [x for x in cleaned if x not in repeated]

    filtered, removed_ref = trim_references(filtered)
    final_text = join_wrapped_lines(filtered)
    return final_text, removed_ref


def validate_quality(raw: str, clean: str, min_clean_len: int) -> Optional[str]:
    c = clean.strip()
    if len(c) < min_clean_len:
        return f"clean_text_too_short:{len(c)}"

    low = c.lower()
    if "document generated by anna’s archive" in low or "document generated by anna's archive" in low:
        return "anna_archive_metadata_only"

    ratio = len(c) / max(len(raw), 1)
    chapter_hits = len(re.findall(r"第\\s*[一二三四五六七八九十0-9]+\\s*[章节]", c))
    section_hits = len(re.findall(r"第\\s*[一二三四五六七八九十0-9]+\\s*节", c))
    if ratio < 0.05 and (chapter_hits + section_hits) >= 8 and ("目录" in c or "目 录" in c):
        return f"toc_only_or_bad_extract:ratio={ratio:.3f}"

    if ratio < 0.03 and len(raw) > 100000:
        return f"extraction_low_yield:ratio={ratio:.3f}"

    return None


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf_text(path)
    if ext == ".docx":
        return extract_docx_text(path)
    raise ValueError(f"unsupported extension: {ext}")


def process_one(path: Path, raw_root: Path, out_docs_dir: Path, min_clean_len: int) -> ParsedDoc:
    rel = path.relative_to(raw_root)
    rel_str = str(rel)
    doc_id = sha1_short(rel_str)
    source_group = rel.parts[0] if rel.parts else "unknown"
    file_type = path.suffix.lower().lstrip(".")

    try:
        raw = extract_text(path)
        clean, removed_ref = clean_text(raw)
        quality_err = validate_quality(raw, clean, min_clean_len)
        if quality_err:
            raise RuntimeError(quality_err)

        lang = detect_language(clean)

        out_payload = {
            "doc_id": doc_id,
            "source_path": str(path),
            "relative_path": rel_str,
            "source_group": source_group,
            "file_type": file_type,
            "language": lang,
            "text": clean,
            "stats": {
                "raw_length": len(raw),
                "clean_length": len(clean),
                "line_count": len(clean.splitlines()),
                "removed_references": removed_ref,
            },
        }
        out_path = out_docs_dir / f"{doc_id}.json"
        out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return ParsedDoc(
            source_path=str(path),
            relative_path=rel_str,
            doc_id=doc_id,
            source_group=source_group,
            file_type=file_type,
            language=lang,
            text_raw_len=len(raw),
            text_clean_len=len(clean),
            line_count_clean=len(clean.splitlines()),
            removed_references=removed_ref,
            status="ok",
        )
    except Exception as exc:
        return ParsedDoc(
            source_path=str(path),
            relative_path=rel_str,
            doc_id=doc_id,
            source_group=source_group,
            file_type=file_type,
            language="unknown",
            text_raw_len=0,
            text_clean_len=0,
            line_count_clean=0,
            removed_references=False,
            status="error",
            error=str(exc),
        )


def write_outputs(results: list[ParsedDoc], out_root: Path) -> None:
    manifest_path = out_root / "manifest.jsonl"
    errors_path = out_root / "logs" / "errors.jsonl"
    summary_path = out_root / "summary.json"

    ok = [r for r in results if r.status == "ok"]
    err = [r for r in results if r.status == "error"]

    with manifest_path.open("w", encoding="utf-8") as mf:
        for r in ok:
            mf.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")

    with errors_path.open("w", encoding="utf-8") as ef:
        for r in err:
            ef.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")

    by_group = Counter(r.source_group for r in ok)
    by_lang = Counter(r.language for r in ok)
    summary = {
        "total": len(results),
        "ok": len(ok),
        "error": len(err),
        "by_group": dict(by_group),
        "by_language": dict(by_lang),
        "avg_clean_length": int(sum(r.text_clean_len for r in ok) / max(len(ok), 1)),
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parse and clean ASD corpus files.")
    p.add_argument("--input", default="data/raw", help="Raw corpus directory")
    p.add_argument("--output", default="data/processed/text", help="Output directory")
    p.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    p.add_argument("--limit", type=int, default=0, help="Process at most N files (0 = all)")
    p.add_argument("--min-clean-len", type=int, default=80, help="Minimum cleaned text length to mark as valid")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    raw_root = Path(args.input).resolve()
    out_root = Path(args.output).resolve()
    out_docs_dir = out_root / "docs"
    out_logs_dir = out_root / "logs"
    out_docs_dir.mkdir(parents=True, exist_ok=True)
    out_logs_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(iter_files(raw_root))
    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print("No input files found.")
        return 1

    print(f"Found {len(files)} files under {raw_root}")

    results: list[ParsedDoc] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(process_one, p, raw_root, out_docs_dir, args.min_clean_len) for p in files]
        for idx, fut in enumerate(as_completed(futs), start=1):
            r = fut.result()
            results.append(r)
            if idx % 20 == 0 or idx == len(files):
                ok_cnt = sum(1 for x in results if x.status == "ok")
                err_cnt = len(results) - ok_cnt
                print(f"[{idx}/{len(files)}] ok={ok_cnt} err={err_cnt}")

    # Keep manifest deterministically ordered by relative path
    results.sort(key=lambda x: x.relative_path)
    write_outputs(results, out_root)

    ok_cnt = sum(1 for x in results if x.status == "ok")
    err_cnt = len(results) - ok_cnt
    print(f"Done. ok={ok_cnt}, err={err_cnt}")
    print(f"Manifest: {out_root / 'manifest.jsonl'}")
    print(f"Errors:   {out_root / 'logs' / 'errors.jsonl'}")
    print(f"Summary:  {out_root / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
