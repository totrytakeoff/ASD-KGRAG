#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

SUPPORTED_SUFFIXES = {".pdf", ".docx"}


def sha1_short(v: str, n: int = 16) -> str:
    return hashlib.sha1(v.encode("utf-8", errors="ignore")).hexdigest()[:n]


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, check=False, capture_output=True)
    return (
        p.returncode,
        p.stdout.decode("utf-8", errors="ignore"),
        p.stderr.decode("utf-8", errors="ignore"),
    )


def has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def parse_pdfinfo(path: Path) -> dict[str, Any]:
    rc, out, err = run_cmd(["pdfinfo", str(path)])
    info: dict[str, Any] = {"ok": rc == 0, "error": err.strip() if rc != 0 else None}
    if rc != 0:
        return info

    for line in out.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        info[k.strip().lower().replace(" ", "_")] = v.strip()

    try:
        info["pages"] = int(str(info.get("pages")))
    except Exception:
        info["pages"] = None
    return info


def extract_pdf_textlayer(path: Path) -> dict[str, Any]:
    rc, out, err = run_cmd(["pdftotext", "-enc", "UTF-8", str(path), "-"])
    if rc != 0:
        return {"ok": False, "text": "", "error": err.strip(), "mode": "pdftotext", "page_texts": []}
    raw_pages = [p.strip() for p in out.split("\f")]
    page_texts = [{"page_id": i + 1, "text": p} for i, p in enumerate(raw_pages) if p]
    merged = "\n\n".join([f"[PAGE {x['page_id']}]\n{x['text']}" for x in page_texts])
    return {"ok": True, "text": merged, "error": None, "mode": "pdftotext", "page_texts": page_texts}


def parse_pdfimages(path: Path) -> dict[str, Any]:
    rc, out, err = run_cmd(["pdfimages", "-list", str(path)])
    if rc != 0:
        return {"ok": False, "error": err.strip(), "rows": [], "summary": {}}

    rows: list[dict[str, Any]] = []
    for ln in out.splitlines():
        if not re.match(r"^\s*\d+\s+", ln):
            continue
        parts = re.split(r"\s+", ln.strip())
        if len(parts) < 10:
            continue
        try:
            rows.append(
                {
                    "page": int(parts[0]),
                    "num": int(parts[1]),
                    "type": parts[2],
                    "width": int(parts[3]),
                    "height": int(parts[4]),
                    "color": parts[5],
                    "enc": parts[8],
                    "size": parts[-2] if len(parts) >= 2 else None,
                    "ratio": parts[-1] if len(parts) >= 1 else None,
                }
            )
        except Exception:
            continue

    pages_with_images = len({r["page"] for r in rows})
    total_pixels = sum((r.get("width") or 0) * (r.get("height") or 0) for r in rows)
    return {
        "ok": True,
        "error": None,
        "rows": rows,
        "summary": {
            "image_count": len(rows),
            "pages_with_images": pages_with_images,
            "total_pixels": total_pixels,
        },
    }


def extract_docx_text(path: Path) -> dict[str, Any]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
            media = [n for n in zf.namelist() if n.startswith("word/media/") and not n.endswith("/")]
    except (BadZipFile, KeyError) as exc:
        return {"ok": False, "text": "", "error": str(exc), "media_count": 0}

    root = ET.fromstring(xml)
    lines: list[str] = []
    for p in root.findall(".//w:p", ns):
        pieces: list[str] = []
        for t in p.findall(".//w:t", ns):
            if t.text:
                pieces.append(t.text)
        if pieces:
            lines.append("".join(pieces))

    return {"ok": True, "text": "\n".join(lines), "error": None, "media_count": len(media)}


def detect_lang(text: str) -> str:
    zh = len(re.findall(r"[\u4e00-\u9fff]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    if zh == 0 and en == 0:
        return "unknown"
    return "zh" if zh >= en else "en"


def ocr_available() -> bool:
    return has_cmd("tesseract") and has_cmd("pdftoppm")


def ocr_pdf_with_tesseract(
    pdf_path: Path,
    pages: int | None,
    dpi: int,
    max_pages: int,
    lang: str,
) -> dict[str, Any]:
    if not ocr_available():
        return {"attempted": True, "ok": False, "reason": "ocr_tool_unavailable", "text": "", "chars": 0, "pages_ocrd": 0}

    upper = pages if pages and pages > 0 else 1
    if max_pages > 0:
        upper = min(upper, max_pages)

    texts: list[dict[str, Any]] = []
    pages_done = 0
    with tempfile.TemporaryDirectory(prefix="asd_ocr_") as td:
        tmp = Path(td)
        for p in range(1, upper + 1):
            img_prefix = tmp / f"p{p:04d}"
            rc, _, err = run_cmd([
                "pdftoppm",
                "-f",
                str(p),
                "-l",
                str(p),
                "-r",
                str(dpi),
                "-png",
                str(pdf_path),
                str(img_prefix),
            ])
            if rc != 0:
                continue
            candidates = sorted(tmp.glob(f"{img_prefix.name}-*.png"))
            if not candidates:
                continue
            img = candidates[0]
            rc2, out2, err2 = run_cmd(["tesseract", str(img), "stdout", "-l", lang, "--psm", "6"])
            if rc2 == 0:
                texts.append({"page_id": p, "text": out2})
                pages_done += 1

    txt = "\n\n".join([f"[PAGE {x['page_id']}]\n{x['text']}" for x in texts])
    return {
        "attempted": True,
        "ok": pages_done > 0 and len(txt.strip()) > 0,
        "reason": None if pages_done > 0 else "ocr_no_pages_processed",
        "text": txt,
        "page_texts": texts,
        "chars": len(txt),
        "pages_ocrd": pages_done,
    }


def should_ocr(textlayer_chars: int, pages: int | None, mode: str, threshold_cpp: float) -> bool:
    if mode == "always":
        return True
    if mode == "off":
        return False
    # auto
    if pages and pages > 0:
        cpp = textlayer_chars / pages
        return cpp < threshold_cpp
    return textlayer_chars < 1000


def process_file(path: Path, input_root: Path, out_docs_dir: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    rel = str(path.relative_to(input_root))
    doc_id = sha1_short(rel)
    source_group = path.relative_to(input_root).parts[0]
    ext = path.suffix.lower()

    base = {
        "doc_id": doc_id,
        "source_path": str(path),
        "relative_path": rel,
        "source_group": source_group,
        "file_type": ext.lstrip("."),
    }

    try:
        if ext == ".pdf":
            info = parse_pdfinfo(path)
            tx = extract_pdf_textlayer(path)
            img = parse_pdfimages(path)

            textlayer = tx.get("text", "")
            pages = info.get("pages") if isinstance(info, dict) else None

            run_ocr = should_ocr(
                textlayer_chars=len(textlayer),
                pages=pages,
                mode=cfg["ocr_mode"],
                threshold_cpp=cfg["ocr_threshold_cpp"],
            )
            ocr = (
                ocr_pdf_with_tesseract(
                    path,
                    pages=pages,
                    dpi=cfg["ocr_dpi"],
                    max_pages=cfg["ocr_max_pages"],
                    lang=cfg["ocr_lang"],
                )
                if run_ocr
                else {"attempted": False, "ok": False, "reason": "ocr_skipped", "text": "", "chars": 0, "pages_ocrd": 0}
            )

            ocr_text = ocr.get("text", "")
            textlayer_pages = tx.get("page_texts", [])
            ocr_pages = ocr.get("page_texts", [])
            if len(ocr_text) > len(textlayer):
                merged = ocr_text
                chosen = "ocr"
                merged_pages = ocr_pages
            else:
                merged = textlayer
                chosen = "textlayer"
                merged_pages = textlayer_pages

            chars = len(merged)
            extracted_pages = ocr.get("pages_ocrd", 0) if chosen == "ocr" else (pages or 0)
            source_pages = pages or 0
            cpp = round(chars / max(source_pages or 1, 1), 2)
            cpp_extracted = round(chars / max(extracted_pages or 1, 1), 2)
            coverage_ratio = round((extracted_pages / source_pages), 4) if source_pages else None

            payload = {
                **base,
                "extract": {
                    "pdfinfo": info,
                    "image_inventory": img,
                    "textlayer": {
                        "ok": tx.get("ok", False),
                        "chars": len(textlayer),
                        "page_count": len(textlayer_pages),
                        "page_texts": textlayer_pages,
                        "text": textlayer,
                        "error": tx.get("error"),
                    },
                    "ocr": {
                        "attempted": ocr.get("attempted", False),
                        "ok": ocr.get("ok", False),
                        "chars": ocr.get("chars", 0),
                        "pages_ocrd": ocr.get("pages_ocrd", 0),
                        "page_texts": ocr_pages,
                        "reason": ocr.get("reason"),
                        "text": ocr_text,
                    },
                    "vision_api": {
                        "attempted": False,
                        "ok": False,
                        "reason": "not_enabled",
                        "notes": "Set OPENAI_API_KEY and integrate optional image captioning step if needed.",
                    },
                    "merged": {
                        "strategy": "max_chars(textlayer,ocr)",
                        "selected_source": chosen,
                        "chars": chars,
                        "chars_per_page": cpp,
                        "chars_per_extracted_page": cpp_extracted,
                        "source_pages": source_pages,
                        "extracted_pages": extracted_pages,
                        "extraction_coverage_ratio": coverage_ratio,
                        "page_texts": merged_pages,
                        "language": detect_lang(merged),
                        "text": merged,
                    },
                },
                "status": "ok",
                "error": None,
            }
        else:
            dx = extract_docx_text(path)
            text = dx.get("text", "")
            payload = {
                **base,
                "extract": {
                    "docx": {
                        "ok": dx.get("ok", False),
                        "media_count": dx.get("media_count", 0),
                        "chars": len(text),
                        "text": text,
                        "error": dx.get("error"),
                    },
                    "merged": {
                        "strategy": "docx_text",
                        "selected_source": "docx",
                        "chars": len(text),
                        "chars_per_page": None,
                        "language": detect_lang(text),
                        "text": text,
                    },
                },
                "status": "ok" if dx.get("ok") else "error",
                "error": dx.get("error"),
            }

        out_path = out_docs_dir / f"{doc_id}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "doc_id": doc_id,
            "relative_path": rel,
            "source_group": source_group,
            "file_type": ext.lstrip("."),
            "status": payload["status"],
            "error": payload["error"],
            "chars": payload["extract"]["merged"]["chars"],
            "language": payload["extract"]["merged"]["language"],
            "chars_per_page": payload["extract"]["merged"]["chars_per_page"],
            "selected_source": payload["extract"]["merged"]["selected_source"],
            "ocr_attempted": payload["extract"].get("ocr", {}).get("attempted", False),
            "ocr_chars": payload["extract"].get("ocr", {}).get("chars", 0),
        }
    except Exception as exc:
        return {
            "doc_id": doc_id,
            "relative_path": rel,
            "source_group": source_group,
            "file_type": ext.lstrip("."),
            "status": "error",
            "error": str(exc),
            "chars": 0,
            "language": "unknown",
            "chars_per_page": None,
            "selected_source": "none",
            "ocr_attempted": False,
            "ocr_chars": 0,
        }


def iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            yield p


def main() -> int:
    ap = argparse.ArgumentParser(description="Raw extraction only (no cleaning).")
    ap.add_argument("--input", default="data/raw")
    ap.add_argument("--output", default="data/processed/extract_raw")
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--path-filter", default="", help="Regex filter applied to relative path")
    ap.add_argument("--list-file", default="", help="Optional file with relative paths, one per line")
    ap.add_argument("--ocr-mode", choices=["off", "auto", "always"], default="auto")
    ap.add_argument("--ocr-threshold-cpp", type=float, default=60.0)
    ap.add_argument("--ocr-dpi", type=int, default=220)
    ap.add_argument("--ocr-max-pages", type=int, default=0, help="0 means all pages")
    ap.add_argument("--ocr-lang", default="chi_sim+eng")
    args = ap.parse_args()

    input_root = Path(args.input).resolve()
    out_root = Path(args.output).resolve()
    out_docs_dir = out_root / "docs"
    out_docs_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "ocr_mode": args.ocr_mode,
        "ocr_threshold_cpp": args.ocr_threshold_cpp,
        "ocr_dpi": args.ocr_dpi,
        "ocr_max_pages": args.ocr_max_pages,
        "ocr_lang": args.ocr_lang,
    }

    files = sorted(iter_files(input_root))
    if args.list_file:
        keep = {x.strip() for x in Path(args.list_file).read_text(encoding="utf-8").splitlines() if x.strip()}
        files = [f for f in files if str(f.relative_to(input_root)) in keep]
    if args.path_filter:
        rx = re.compile(args.path_filter)
        files = [f for f in files if rx.search(str(f.relative_to(input_root)))]
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        print("No supported files found")
        return 1

    print(f"Found {len(files)} files")

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(process_file, f, input_root, out_docs_dir, cfg) for f in files]
        for i, fut in enumerate(as_completed(futs), start=1):
            results.append(fut.result())
            if i % 10 == 0 or i == len(files):
                ok = sum(1 for r in results if r["status"] == "ok")
                err = len(results) - ok
                print(f"[{i}/{len(files)}] ok={ok} err={err}")

    results.sort(key=lambda x: x["relative_path"])
    manifest_path = out_root / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "total": len(results),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "error": sum(1 for r in results if r["status"] != "ok"),
        "ocr_mode": args.ocr_mode,
        "ocr_available": ocr_available(),
        "ocr_attempted_docs": sum(1 for r in results if r.get("ocr_attempted")),
        "ocr_selected_docs": sum(1 for r in results if r.get("selected_source") == "ocr"),
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False))
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
