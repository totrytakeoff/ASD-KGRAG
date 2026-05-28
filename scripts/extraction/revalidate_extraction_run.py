#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from extract_entities_relations import load_json, validate_record


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-apply current extraction validation rules to an existing extraction JSONL.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--schema", default="scripts/extraction/entity_relation_schema.json")
    args = ap.parse_args()

    schema = load_json(Path(args.schema).resolve())
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    summary = {"rows": 0, "ok": 0, "error": 0, "entity_count": 0, "relation_count": 0}
    for row in iter_jsonl(Path(args.input).resolve()):
        summary["rows"] += 1
        if row.get("status") != "ok":
            rows.append(row)
            summary["error"] += 1
            continue

        raw = {
            "entities": row.get("entities", []),
            "relations": row.get("relations", []),
        }
        entities, relations, warnings = validate_record(raw, schema)
        new_row = dict(row)
        new_row["warnings"] = warnings
        new_row["entities"] = entities
        new_row["relations"] = relations
        rows.append(new_row)
        summary["ok"] += 1
        summary["entity_count"] += len(entities)
        summary["relation_count"] += len(relations)

    out_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({**summary, "output": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
