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


def choose_record(current: dict | None, candidate: dict) -> dict:
    if current is None:
        return candidate
    current_ok = current.get("status") == "ok"
    candidate_ok = candidate.get("status") == "ok"
    if candidate_ok and not current_ok:
        return candidate
    if candidate_ok == current_ok:
        return candidate
    return current


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge multiple extraction jsonl outputs by chunk_id")
    ap.add_argument("--inputs", nargs="+", required=True, help="chunk_extractions.jsonl files in priority order")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    merged: dict[str, dict] = {}
    order: list[str] = []
    for path_str in args.inputs:
        for row in iter_jsonl(Path(path_str)):
            chunk_id = row.get("chunk_id")
            if not chunk_id:
                continue
            if chunk_id not in merged:
                order.append(chunk_id)
            merged[chunk_id] = choose_record(merged.get(chunk_id), row)

    out_rows = [merged[chunk_id] for chunk_id in order]
    Path(args.output).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in out_rows), encoding="utf-8")
    print(json.dumps({
        "output": args.output,
        "rows": len(out_rows),
        "ok": sum(1 for row in out_rows if row.get("status") == "ok"),
        "error": sum(1 for row in out_rows if row.get("status") == "error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
