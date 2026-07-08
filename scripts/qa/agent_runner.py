#!/usr/bin/env python3
"""CLI entry point for the first controlled KGRAG agent workflow."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from agent_tools import open_agent_resources, run_toolized_agent  # noqa: E402
from agent_trace import AgentTrace  # noqa: E402
from kgrag_answer import default_namespace, load_dotenv  # noqa: E402


def parse_args() -> argparse.Namespace:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Run the controlled KGRAG agent workflow.")
    ap.add_argument("--query", required=True)
    ap.add_argument("--keywords", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--trace-out", type=Path, default=None)
    ap.add_argument("--json", action="store_true", help="Print the full JSON result.")
    ap.add_argument("--context-k", type=int, default=6)
    ap.add_argument("--graph-evidence-k", type=int, default=4)
    ap.add_argument("--retrieval-k", type=int, default=20)
    ap.add_argument("--relation-k", type=int, default=30)
    ap.add_argument("--relation-evidence-k", type=int, default=6)
    ap.add_argument("--graph-evidence-pool-k", type=int, default=30)
    ap.add_argument("--max-chars-per-chunk", type=int, default=900)
    return ap.parse_args()


def to_namespace(cli_args: argparse.Namespace):
    return default_namespace(
        query=cli_args.query,
        keywords=cli_args.keywords,
        dry_run=cli_args.dry_run,
        context_k=cli_args.context_k,
        graph_evidence_k=cli_args.graph_evidence_k,
        retrieval_k=cli_args.retrieval_k,
        relation_k=cli_args.relation_k,
        relation_evidence_k=cli_args.relation_evidence_k,
        graph_evidence_pool_k=cli_args.graph_evidence_pool_k,
        max_chars_per_chunk=cli_args.max_chars_per_chunk,
    )


def print_summary(result: dict) -> None:
    agent = result.get("agent") or {}
    intent = (agent.get("intent") or {}).get("intent")
    evidence = agent.get("evidence") or {}
    validation = agent.get("validation") or {}
    context = result.get("context") or {}
    print(f"query: {result.get('query')}")
    print(f"dry_run: {result.get('dry_run')}")
    print(f"intent: {intent}")
    print(f"contexts: {len(context.get('contexts') or [])}")
    print(f"relations: {len(context.get('relations') or [])}")
    print(f"evidence_flags: {json.dumps(evidence.get('flags') or {}, ensure_ascii=False)}")
    print(f"validation_ok: {validation.get('ok')}")
    if result.get("dry_run"):
        print(f"prompt_preview_chars: {len(result.get('prompt_preview') or '')}")
    elif result.get("answer"):
        print()
        print(result["answer"])


def main() -> int:
    cli_args = parse_args()
    args = to_namespace(cli_args)
    trace = AgentTrace(query=args.query)
    with ExitStack() as stack:
        driver, embed_model, qdrant_client = open_agent_resources(stack, args)
        result = run_toolized_agent(
            args,
            driver=driver,
            embed_model=embed_model,
            qdrant_client=qdrant_client,
            trace=trace,
        )
    if cli_args.trace_out:
        trace.write_json(cli_args.trace_out)
    if cli_args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
