#!/usr/bin/env python3
"""Dependency-free HTTP API for the KGRAG QA prototype."""
from __future__ import annotations

import argparse
import json
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from kgrag_answer import answer_query, default_namespace, load_dotenv  # noqa: E402


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def parse_int(payload: dict, key: str, default: int) -> int:
    value = payload.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class KGRAGHandler(BaseHTTPRequestHandler):
    server_version = "ASD-KGRAG-QA/0.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "kgrag-qa",
                    "time": int(time.time()),
                },
            )
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:
        if self.path != "/ask":
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found", "path": self.path})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_json", "detail": str(exc)})
            return

        query = str(payload.get("query") or "").strip()
        if not query:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "query_required"})
            return

        args = default_namespace(
            query=query,
            keywords=payload.get("keywords") or [],
            dry_run=parse_bool(payload.get("dry_run"), False),
            retrieval_k=parse_int(payload, "retrieval_k", 20),
            context_k=parse_int(payload, "context_k", 6),
            relation_k=parse_int(payload, "relation_k", 30),
            relation_evidence_k=parse_int(payload, "relation_evidence_k", 6),
            graph_evidence_k=parse_int(payload, "graph_evidence_k", 4),
            graph_evidence_pool_k=parse_int(payload, "graph_evidence_pool_k", 30),
            max_chars_per_chunk=parse_int(payload, "max_chars_per_chunk", 900),
        )

        try:
            result = answer_query(args)
        except Exception as exc:
            json_response(
                self,
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "qa_failed",
                    "detail": str(exc),
                },
            )
            return

        json_response(self, HTTPStatus.OK, result)


def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Serve KGRAG QA over HTTP.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), KGRAGHandler)
    print(f"KGRAG QA API listening on http://{args.host}:{args.port}")
    print("GET /health")
    print("POST /ask {\"query\": \"...\", \"dry_run\": true}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
