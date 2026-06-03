#!/usr/bin/env python3
"""Embed chunk texts and write vectors to Qdrant."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as rf:
        for line in rf:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_payload(chunk: dict) -> dict:
    return {
        "chunk_id": chunk.get("chunk_id", ""),
        "doc_id": chunk.get("doc_id", ""),
        "title": chunk.get("title", ""),
        "year": chunk.get("year"),
        "evidence_level": chunk.get("evidence_level", ""),
        "source_type": chunk.get("source_type", ""),
        "heading_path": chunk.get("heading_path", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Embed chunks and write to Qdrant")
    ap.add_argument("--input", default="data/processed/chunks_extractable_full_ab_nonbook.jsonl")
    ap.add_argument("--collection", default="asd_kgrag_chunks")
    ap.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    ap.add_argument("--qdrant-api-key", default=os.environ.get("QDRANT_API_KEY", ""))
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start-index", type=int, default=0)
    ap.add_argument("--recreate", action="store_true", help="Drop and recreate collection")
    args = ap.parse_args()

    chunks_path = Path(args.input).resolve()
    if not chunks_path.exists():
        print(f"input not found: {chunks_path}")
        return 1

    # Load chunks
    rows = list(iter_jsonl(chunks_path))
    if args.start_index > 0:
        rows = rows[args.start_index:]
    if args.limit > 0:
        rows = rows[:args.limit]
    print(f"loaded {len(rows)} chunks from {chunks_path}")

    # Load model
    print(f"loading model {args.model}...")
    t0 = time.time()
    model = SentenceTransformer(args.model)
    dim = model.get_embedding_dimension()
    print(f"model loaded in {time.time()-t0:.1f}s, dim={dim}")

    # Connect to Qdrant
    client_kwargs = {"url": args.qdrant_url}
    if args.qdrant_api_key:
        client_kwargs["api_key"] = args.qdrant_api_key
    client = QdrantClient(**client_kwargs)

    # Create or recreate collection
    if args.recreate:
        client.delete_collection(collection_name=args.collection)
        print(f"deleted collection {args.collection}")

    collections = [c.name for c in client.get_collections().collections]
    if args.collection not in collections:
        client.create_collection(
            collection_name=args.collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        print(f"created collection {args.collection} (dim={dim}, cosine)")
    else:
        print(f"collection {args.collection} exists")

    # Encode and upload in batches
    total_written = 0
    for batch_start in range(0, len(rows), args.batch_size):
        batch = rows[batch_start:batch_start + args.batch_size]
        texts = [chunk.get("text", "") for chunk in batch]
        vectors = model.encode(texts, show_progress_bar=False, batch_size=len(batch))

        points = []
        for i, chunk in enumerate(batch):
            vec = vectors[i].tolist()
            # Use a stable numeric ID from chunk_id hash
            point_id = abs(hash(chunk.get("chunk_id", f"idx_{batch_start+i}"))) % (2**63)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=build_payload(chunk),
                )
            )

        client.upsert(collection_name=args.collection, points=points)
        total_written += len(points)
        if (batch_start // args.batch_size) % 5 == 0 or batch_start + args.batch_size >= len(rows):
            print(f"  [{total_written}/{len(rows)}] vectors written")

    print(f"done: {total_written} vectors in collection {args.collection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
