#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build retry chunk input from timed-out/error extraction rows")
    ap.add_argument("--input", required=True, help="Original chunk jsonl")
    ap.add_argument("--extraction", required=True, help="chunk_extractions.jsonl from a run")
    ap.add_argument("--output", required=True, help="Retry chunk jsonl")
    ap.add_argument("--only-timeouts", action="store_true", default=False)
    ap.add_argument("--transient-errors", action="store_true", default=False)
    ap.add_argument("--error-substring", action="append", default=[])
    args = ap.parse_args()

    transient_markers = (
        "timed out",
        "ssl:",
        "unexpected_eof",
        "remote end closed",
        "temporary failure in name resolution",
        "urlopen error",
        "network error",
    )

    error_ids: set[str] = set()
    for row in iter_jsonl(Path(args.extraction)):
        if row.get("status") != "error":
            continue
        error_text = (row.get("error", "") or "").lower()
        if args.only_timeouts or args.transient_errors or args.error_substring:
            keep = True
            if args.only_timeouts:
                keep = "timed out" in error_text
            if args.transient_errors:
                keep = any(marker in error_text for marker in transient_markers)
            if args.error_substring:
                keep = any(marker.lower() in error_text for marker in args.error_substring)
            if not keep:
                continue
        chunk_id = row.get("chunk_id")
        if chunk_id:
            error_ids.add(chunk_id)

    selected = [row for row in iter_jsonl(Path(args.input)) if row.get("chunk_id") in error_ids]
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    print(json.dumps({
        "input": args.input,
        "extraction": args.extraction,
        "output": args.output,
        "retry_count": len(selected),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
