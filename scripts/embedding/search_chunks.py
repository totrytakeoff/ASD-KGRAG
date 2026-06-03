#!/usr/bin/env python3
"""Search Qdrant chunk collection for debugging."""
from __future__ import annotations

import argparse
import os

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient


def main() -> int:
    ap = argparse.ArgumentParser(description="Search chunks in Qdrant")
    ap.add_argument("query", help="Search query text")
    ap.add_argument("--collection", default="asd_kgrag_chunks")
    ap.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument("--qdrant-api-key", default=os.environ.get("QDRANT_API_KEY", ""))
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    model = SentenceTransformer(args.model)
    query_vec = model.encode([args.query])[0].tolist()

    client_kwargs = {"url": args.qdrant_url}
    if args.qdrant_api_key:
        client_kwargs["api_key"] = args.qdrant_api_key
    client = QdrantClient(**client_kwargs)

    results = client.query_points(
        collection_name=args.collection,
        query=query_vec,
        limit=args.top_k,
    )

    for i, point in enumerate(results.points, 1):
        p = point.payload
        score = point.score
        print(f"--- #{i} score={score:.4f} ---")
        print(f"  chunk_id: {p.get('chunk_id')}")
        print(f"  title: {p.get('title')}")
        print(f"  year: {p.get('year')}")
        print(f"  evidence_level: {p.get('evidence_level')}")
        print(f"  source_type: {p.get('source_type')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
