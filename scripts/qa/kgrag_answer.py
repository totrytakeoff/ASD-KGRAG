#!/usr/bin/env python3
"""Minimal KGRAG QA prototype: hybrid retrieval + guarded LLM answer."""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrieval"))

from hybrid_search import (  # noqa: E402
    DEFAULT_COLLECTION,
    DEFAULT_MODEL,
    NEO4J_DEFAULT_PASS,
    NEO4J_DEFAULT_URL,
    NEO4J_DEFAULT_USER,
    QDRANT_DEFAULT_URL,
    graph_search,
    merge_results,
    vector_search,
)


DEFAULT_LLM_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"


DEFAULT_QA_OPTIONS = {
    "retrieval_k": 20,
    "context_k": 6,
    "relation_k": 30,
    "relation_evidence_k": 6,
    "graph_evidence_k": 4,
    "graph_evidence_pool_k": 30,
    "max_chars_per_chunk": 900,
}


def normalize_alias_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def add_alias_payload(alias_map: dict[str, list[str]], payload: dict) -> None:
    for group in payload.get("groups", []):
        terms = [group.get("group_id", ""), *(group.get("aliases") or [])]
        terms = [term for term in terms if term]
        expanded = sorted(set(terms))
        for term in expanded:
            key = normalize_alias_key(term)
            existing = alias_map.get(key, [])
            alias_map[key] = sorted(set([*existing, *expanded]))


def load_query_aliases(path: Path | None = None) -> dict[str, list[str]]:
    paths = [
        ROOT / "config" / "graph" / "curated_entity_alias_map.json",
        ROOT / "config" / "qa" / "query_alias_map.json",
    ]
    if path is not None:
        paths = [path]
    alias_map: dict[str, list[str]] = {}
    for alias_path in paths:
        if not alias_path.exists():
            continue
        payload = json.loads(alias_path.read_text(encoding="utf-8"))
        add_alias_payload(alias_map, payload)
    return alias_map


def expand_keywords(keywords: list[str]) -> list[str]:
    alias_map = load_query_aliases()
    expanded = []
    for keyword in keywords:
        expanded.append(keyword)
        expanded.extend(alias_map.get(normalize_alias_key(keyword), []))
    seen = set()
    deduped = []
    for keyword in expanded:
        key = normalize_alias_key(keyword)
        if key and key not in seen:
            seen.add(key)
            deduped.append(keyword)
    return deduped


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def auto_keywords(query: str) -> list[str]:
    stopwords = {
        "是什么",
        "什么",
        "它在",
        "有什么作用",
        "作用",
        "评估中有什么作用",
    }
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]*|[\u4e00-\u9fff]{2,}", query)
    keywords = []
    for token in tokens:
        lowered = token.lower()
        if lowered in stopwords:
            continue
        if any(word in lowered for word in ("什么", "作用")):
            continue
        keywords.append(token)
    return sorted(set(keywords)) if keywords else [query]


def compact_query_text(parts: list[str], max_chars: int = 220) -> str:
    text = " ".join(part for part in parts if part)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def build_vector_queries(query: str, keywords: list[str]) -> list[str]:
    generic = {"asd", "autism", "孤独症", "自闭症", "孤独症谱系障碍", "自闭症谱系障碍"}
    specific = [
        keyword
        for keyword in keywords
        if keyword and keyword.lower() not in generic
    ]
    variants = [query]
    if specific:
        variants.append(compact_query_text(specific))
        variants.append(compact_query_text([query, *specific[:8]]))
    seen = set()
    deduped = []
    for variant in variants:
        key = normalize_alias_key(variant)
        if key and key not in seen:
            seen.add(key)
            deduped.append(variant)
    return deduped[:3]


def vector_search_variants(qdrant_client, embed_model, queries: list[str], collection: str, top_k: int) -> list[dict]:
    by_chunk_id: dict[str, dict] = {}
    per_query_k = max(top_k, min(40, top_k * 2))
    for idx, query in enumerate(queries):
        for hit in vector_search(qdrant_client, embed_model, query, collection, per_query_k):
            chunk_id = hit.get("chunk_id")
            if not chunk_id:
                continue
            score = float(hit.get("score") or 0.0)
            existing = by_chunk_id.get(chunk_id)
            if existing is None or score > float(existing.get("score") or 0.0):
                merged = dict(hit)
                merged["vector_query"] = query
                merged["vector_query_rank"] = idx
                by_chunk_id[chunk_id] = merged
    hits = list(by_chunk_id.values())
    hits.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    return hits[:top_k]


def fetch_chunks(driver, chunk_ids: list[str]) -> dict[str, dict]:
    if not chunk_ids:
        return {}
    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:Chunk)
            WHERE c.chunk_id IN $chunk_ids
            RETURN c.chunk_id AS chunk_id,
                   c.doc_id AS doc_id,
                   c.title AS title,
                   c.year AS year,
                   c.evidence_level AS evidence_level,
                   c.source_type AS source_type,
                   c.page_start AS page_start,
                   c.page_end AS page_end,
                   c.text AS text
            """,
            chunk_ids=chunk_ids,
        )
        return {rec["chunk_id"]: dict(rec) for rec in result}


def fetch_relation_context(driver, entity_ids: list[str], limit: int = 30) -> list[dict]:
    if not entity_ids:
        return []
    with driver.session() as session:
        result = session.run(
            """
            MATCH (src:Entity)-[r]->(dst:Entity)
            WHERE src.entity_id IN $entity_ids OR dst.entity_id IN $entity_ids
            RETURN src.name AS source,
                   src.entity_id AS source_id,
                   src.type AS source_type,
                   type(r) AS relation,
                   dst.name AS target,
                   dst.entity_id AS target_id,
                   dst.type AS target_type,
                   r.relation_id AS relation_id,
                   r.support_count AS support_count,
                   r.confidence AS confidence,
                   r.qa_usage AS qa_usage,
                   r.evidence_level_summary AS evidence_level_summary
            ORDER BY coalesce(r.support_count, 0) DESC, coalesce(r.confidence, 0.0) DESC
            LIMIT $limit
            """,
            entity_ids=entity_ids,
            limit=limit,
        )
        return [dict(rec) for rec in result]


def fetch_relation_evidence_chunks(driver, relation_ids: list[str], limit: int) -> list[dict]:
    if not relation_ids:
        return []
    with driver.session() as session:
        result = session.run(
            """
            UNWIND range(0, size($relation_ids) - 1) AS idx
            WITH idx, $relation_ids[idx] AS relation_id
            MATCH (src:Entity)-[s:SUPPORTED_BY {relation_id: relation_id}]->(ev:Evidence)-[:FROM_CHUNK]->(c:Chunk)
            RETURN DISTINCT s.relation_id AS relation_id,
                   idx AS relation_rank,
                   c.chunk_id AS chunk_id,
                   c.doc_id AS doc_id,
                   c.title AS title,
                   c.year AS year,
                   c.evidence_level AS evidence_level,
                   c.source_type AS source_type,
                   c.page_start AS page_start,
                   c.page_end AS page_end,
                   c.text AS text
            ORDER BY relation_rank
            LIMIT $limit
            """,
            relation_ids=relation_ids,
            limit=limit,
        )
        return [dict(rec) for rec in result]


def fetch_entity_evidence_chunks(driver, entity_ids: list[str], limit: int) -> list[dict]:
    if not entity_ids:
        return []
    with driver.session() as session:
        result = session.run(
            """
            UNWIND range(0, size($entity_ids) - 1) AS idx
            WITH idx, $entity_ids[idx] AS entity_id
            MATCH (e:Entity {entity_id: entity_id})-[:SUPPORTED_BY]->(ev:Evidence)-[:FROM_CHUNK]->(c:Chunk)
            RETURN DISTINCT e.entity_id AS entity_id,
                   e.name AS entity_name,
                   idx AS entity_rank,
                   c.chunk_id AS chunk_id,
                   c.doc_id AS doc_id,
                   c.title AS title,
                   c.year AS year,
                   c.evidence_level AS evidence_level,
                   c.source_type AS source_type,
                   c.page_start AS page_start,
                   c.page_end AS page_end,
                   c.text AS text
            ORDER BY entity_rank
            LIMIT $limit
            """,
            entity_ids=entity_ids,
            limit=limit,
        )
        return [dict(rec) for rec in result]


def chunk_relevance(row: dict, keywords: list[str]) -> tuple[float, float]:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ("title", "text", "evidence_level", "source_type")
    ).lower()
    score = 0.0
    generic_keywords = {"asd", "autism", "孤独症", "自闭症"}
    for keyword in keywords:
        lowered = keyword.lower()
        if lowered and lowered in haystack:
            score += 3.0 if lowered in generic_keywords else 30.0
    evidence_weight = {"S": 5.0, "A": 3.0, "B": 1.0, "C": 0.0, "D": -1.0}
    score += evidence_weight.get(row.get("evidence_level") or "", 0.0)
    rank = row.get("relation_rank")
    if rank is None:
        rank = row.get("entity_rank") or 0
    return score, -float(rank)


def specific_keywords(keywords: list[str]) -> list[str]:
    generic_keywords = {"asd", "autism", "孤独症", "自闭症"}
    return [keyword for keyword in keywords if keyword.lower() not in generic_keywords]


def keyword_matches_chunk(row: dict, keywords: list[str]) -> bool:
    if not keywords:
        return False
    haystack = " ".join(str(row.get(key) or "") for key in ("title", "text")).lower()
    return any(keyword.lower() in haystack for keyword in keywords if keyword)


def entity_matches_keywords(entity: dict, keywords: list[str]) -> bool:
    haystack = " ".join(
        str(entity.get(key) or "")
        for key in ("name", "type")
    ).lower()
    return any(keyword.lower() in haystack for keyword in keywords if keyword)


def relation_relevance(row: dict, keywords: list[str]) -> tuple[float, int, float]:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ("source", "source_type", "relation", "target", "target_type")
    ).lower()
    score = 0.0
    generic_keywords = {"asd", "autism", "孤独症", "自闭症"}
    for keyword in keywords:
        lowered = keyword.lower()
        if not lowered:
            continue
        if lowered in haystack:
            score += 10.0 if lowered in generic_keywords else 100.0
    if row.get("relation") == "MEASURED_BY":
        score += 15.0
    if row.get("target_type") == "AssessmentTool" or row.get("source_type") == "AssessmentTool":
        score += 10.0
    return (
        score,
        int(row.get("support_count") or 0),
        float(row.get("confidence") or 0.0),
    )


def retrieve_context(args, *, driver=None, embed_model=None, qdrant_client=None) -> dict:
    keywords = expand_keywords(args.keywords if args.keywords else auto_keywords(args.query))
    own_driver = driver is None
    if own_driver:
        driver = GraphDatabase.driver(args.neo4j_url, auth=(args.neo4j_user, args.neo4j_pass))
    if embed_model is None:
        embed_model = SentenceTransformer(args.model)
    if qdrant_client is None:
        qdrant_client = QdrantClient(url=args.qdrant_url)
    try:
        graph_result = graph_search(driver, keywords)
        vector_queries = build_vector_queries(args.query, keywords)
        vector_hits = vector_search_variants(
            qdrant_client,
            embed_model,
            vector_queries,
            args.collection,
            args.retrieval_k,
        )
        merged_hits = merge_results(graph_result["chunk_ids"], vector_hits)

        specific = specific_keywords(keywords)
        specific_entities = [
            entity
            for entity in graph_result["entities"]
            if entity.get("entity_id") and entity_matches_keywords(entity, specific)
        ]
        relation_entities = specific_entities or [
            entity for entity in graph_result["entities"] if entity.get("entity_id")
        ]
        entity_ids = [entity["entity_id"] for entity in relation_entities]
        relations = fetch_relation_context(driver, entity_ids, args.relation_k)
        relations.sort(key=lambda row: relation_relevance(row, keywords), reverse=True)
        relation_ids = [
            row["relation_id"]
            for row in relations
            if row.get("relation_id") and row.get("support_count")
        ][: args.relation_evidence_k]
        graph_evidence_pool = fetch_relation_evidence_chunks(driver, relation_ids, args.graph_evidence_pool_k)
        if specific:
            specific_graph_evidence = [
                row for row in graph_evidence_pool if keyword_matches_chunk(row, specific)
            ]
            graph_evidence_pool = specific_graph_evidence
        if len(graph_evidence_pool) < args.graph_evidence_k and specific_entities:
            entity_evidence = fetch_entity_evidence_chunks(
                driver,
                [entity["entity_id"] for entity in specific_entities],
                args.graph_evidence_pool_k,
            )
            if specific:
                entity_evidence = [
                    row for row in entity_evidence if keyword_matches_chunk(row, specific)
                ]
            seen_evidence_chunks = {row.get("chunk_id") for row in graph_evidence_pool}
            graph_evidence_pool.extend(
                row for row in entity_evidence if row.get("chunk_id") not in seen_evidence_chunks
            )
        graph_evidence_pool.sort(key=lambda row: chunk_relevance(row, keywords), reverse=True)
        graph_evidence = graph_evidence_pool[: args.graph_evidence_k]

        selected_hits = merged_hits[: max(0, args.context_k - len(graph_evidence))]
        selected_chunk_ids = [hit["chunk_id"] for hit in selected_hits if hit.get("chunk_id")]
        graph_evidence_chunk_ids = [row["chunk_id"] for row in graph_evidence if row.get("chunk_id")]
        graph_only_chunk_ids = [
            chunk_id
            for chunk_id in graph_result["chunk_ids"]
            if chunk_id not in set(selected_chunk_ids + graph_evidence_chunk_ids)
        ][: max(0, args.context_k - len(selected_chunk_ids))]
        chunk_ids = selected_chunk_ids + graph_only_chunk_ids
        chunks_by_id = fetch_chunks(driver, chunk_ids)

        contexts = []
        seen_chunk_ids = set()
        for item in graph_evidence:
            chunk_id = item.get("chunk_id")
            if not chunk_id or chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            contexts.append(
                {
                    "citation_id": f"C{len(contexts) + 1}",
                    "retrieval": "graph-evidence",
                    "score": 0.0,
                    **item,
                }
            )
        for hit in selected_hits:
            if hit.get("chunk_id") in seen_chunk_ids:
                continue
            chunk = chunks_by_id.get(hit.get("chunk_id"), {})
            if not chunk:
                continue
            seen_chunk_ids.add(hit.get("chunk_id"))
            contexts.append(
                {
                    "citation_id": f"C{len(contexts) + 1}",
                    "retrieval": "graph+vector" if hit.get("in_graph") else "vector",
                    "score": round(float(hit.get("merged_score", 0.0)), 4),
                    **chunk,
                }
            )
        for chunk_id in graph_only_chunk_ids:
            if chunk_id in seen_chunk_ids:
                continue
            chunk = chunks_by_id.get(chunk_id, {})
            if not chunk:
                continue
            seen_chunk_ids.add(chunk_id)
            contexts.append(
                {
                    "citation_id": f"C{len(contexts) + 1}",
                    "retrieval": "graph",
                    "score": 0.0,
                    **chunk,
                }
            )
        contexts = contexts[: args.context_k]
    finally:
        if own_driver:
            driver.close()

    return {
        "query": args.query,
        "keywords": keywords,
        "vector_queries": vector_queries,
        "graph": graph_result,
        "contexts": contexts,
        "relations": relations,
    }


def evidence_policy(relations: list[dict]) -> dict:
    usages = {row.get("qa_usage") for row in relations if row.get("qa_usage")}
    return {
        "requires_clinical_guardrail": "guardrailed_clinical_context" in usages,
        "has_research_only_context": "research_context_only" in usages,
        "has_caution_context": "use_with_caution" in usages,
    }


def keyword_hit_spans(text: str, keywords: list[str]) -> list[tuple[int, int, str]]:
    lowered = text.lower()
    spans = []
    seen_keywords = set()
    for keyword in keywords:
        needle = (keyword or "").strip().lower()
        if not needle or needle in seen_keywords:
            continue
        seen_keywords.add(needle)
        start = 0
        while True:
            pos = lowered.find(needle, start)
            if pos < 0:
                break
            spans.append((pos, pos + len(needle), needle))
            start = pos + max(1, len(needle))
    spans.sort(key=lambda item: (item[0], item[1]))
    return spans


def best_keyword_window(text_len: int, max_chars: int, spans: list[tuple[int, int, str]]) -> tuple[int, int]:
    if text_len <= max_chars:
        return 0, text_len
    if not spans:
        return 0, min(text_len, max_chars)

    candidates = {0, max(0, text_len - max_chars)}
    for start, end, _keyword in spans:
        candidates.add(max(0, min(start - max_chars // 3, text_len - max_chars)))
        candidates.add(max(0, min(end - (max_chars * 2 // 3), text_len - max_chars)))

    best_start = 0
    best_score = (-1, -1, -1, 0)
    for candidate in candidates:
        window_end = min(text_len, candidate + max_chars)
        window_hits = [
            (start, end, keyword)
            for start, end, keyword in spans
            if start < window_end and end > candidate
        ]
        if not window_hits:
            continue
        unique_keywords = {keyword for _start, _end, keyword in window_hits}
        covered_chars = sum(
            max(0, min(end, window_end) - max(start, candidate))
            for start, end, _keyword in window_hits
        )
        first_hit = min(start for start, _end, _keyword in window_hits)
        score = (len(unique_keywords), len(window_hits), covered_chars, -first_hit)
        if score > best_score:
            best_score = score
            best_start = candidate
    return best_start, min(text_len, best_start + max_chars)


def trim_text(text: str, max_chars: int, keywords: list[str] | None = None) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    keywords = keywords or []
    if max_chars <= 0:
        return ""
    if len(text) > max_chars:
        spans = keyword_hit_spans(text, keywords)
        start, end = best_keyword_window(len(text), max_chars, spans)
        snippet = text[start:end]
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{snippet}{suffix}"
    return text


def build_prompt(context: dict, max_chars_per_chunk: int) -> list[dict]:
    policy = evidence_policy(context["relations"])
    evidence_blocks = []
    for item in context["contexts"]:
        pages = ""
        if item.get("page_start") or item.get("page_end"):
            pages = f", pages={item.get('page_start')}-{item.get('page_end')}"
        evidence_blocks.append(
            "\n".join(
                [
                    f"[{item['citation_id']}] {item.get('title') or ''} ({item.get('year') or 'n.d.'}, evidence={item.get('evidence_level') or 'unknown'}, retrieval={item.get('retrieval')}, score={item.get('score')}{pages})",
                    trim_text(item.get("text", ""), max_chars_per_chunk, specific_keywords(context["keywords"]) or context["keywords"]),
                ]
            )
        )

    relation_lines = []
    for idx, row in enumerate(context["relations"][:20], 1):
        relation_lines.append(
            f"[G{idx}] {row.get('source')} ({row.get('source_type')}) -{row.get('relation')}-> "
            f"{row.get('target')} ({row.get('target_type')}), support={row.get('support_count')}, "
            f"confidence={row.get('confidence')}, qa_usage={row.get('qa_usage')}"
        )

    system = """你是 ASD 领域 KGRAG 问答助手。只能基于给定证据回答。
要求：
1. 用中文回答，结构清晰。
2. 每个关键结论后标注引用；文献证据用 [C1]，图谱关系用 [G1]，不要使用“图谱关系”等泛称。
3. 如果证据不足，明确说“不足以支持结论”。
4. 对诊断、干预、用药、风险相关问题必须给出非医疗建议护栏：不能替代专业评估或临床决策。
5. 研究模态、算法、低置信或单证据关系只能作为研究背景，不要写成临床确定结论。"""

    user = f"""用户问题：
{context['query']}

图谱回答策略：
{json.dumps(policy, ensure_ascii=False)}

相关图关系：
{chr(10).join(relation_lines) if relation_lines else '无'}

检索证据：
{chr(10).join(evidence_blocks) if evidence_blocks else '无'}

请给出回答，包含：
- 简短结论
- 证据要点
- 注意事项/证据边界
- 引用列表，分别列出使用过的 [C*] 文献证据和 [G*] 图谱关系"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_openai_compatible(
    *,
    model: str,
    messages: list[dict],
    base_url: str,
    api_key: str,
    timeout_seconds: float,
    max_retries: int,
    max_tokens: int,
) -> str:
    normalized_base = base_url.rstrip("/")
    if normalized_base.endswith("/chat/completions"):
        chat_url = normalized_base
    else:
        chat_url = urllib.parse.urljoin(f"{normalized_base}/", "chat/completions")

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if max_tokens > 0:
        body["max_tokens"] = max_tokens
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    attempt = 0
    while True:
        req = urllib.request.Request(chat_url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            retriable = exc.code in {429, 500, 502, 503, 504}
            if retriable and attempt < max_retries:
                attempt += 1
                time.sleep(attempt)
                continue
            raise RuntimeError(f"LLM API error: {exc.code} {detail}") from exc
        except (
            TimeoutError,
            socket.timeout,
            ConnectionError,
            ConnectionResetError,
            ssl.SSLError,
            urllib.error.URLError,
        ) as exc:
            if attempt < max_retries:
                attempt += 1
                time.sleep(attempt)
                continue
            raise RuntimeError(f"LLM network error: {exc}") from exc


def format_dry_run(context: dict, messages: list[dict]) -> str:
    lines = [
        f"query: {context['query']}",
        f"keywords: {', '.join(context['keywords'])}",
        f"graph: {len(context['graph']['entities'])} entities, {len(context['graph']['relations'])} relations, {len(context['graph']['chunk_ids'])} chunks",
        f"contexts: {len(context['contexts'])}",
        "",
        "top contexts:",
    ]
    for item in context["contexts"]:
        lines.append(
            f"- [{item['citation_id']}] {item.get('retrieval')} score={item.get('score')} "
            f"evidence={item.get('evidence_level')} title={item.get('title')}"
        )
    lines.extend(["", "prompt preview:", messages[-1]["content"][:3000]])
    return "\n".join(lines)


def default_namespace(**overrides) -> SimpleNamespace:
    load_dotenv(ROOT / ".env")
    values = {
        "query": "",
        "keywords": [],
        "neo4j_url": os.environ.get("NEO4J_URL", NEO4J_DEFAULT_URL),
        "neo4j_user": os.environ.get("NEO4J_USER", NEO4J_DEFAULT_USER),
        "neo4j_pass": os.environ.get("NEO4J_PASS", NEO4J_DEFAULT_PASS),
        "qdrant_url": os.environ.get("QDRANT_URL", QDRANT_DEFAULT_URL),
        "collection": os.environ.get("QDRANT_COLLECTION", DEFAULT_COLLECTION),
        "model": os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL),
        "dry_run": False,
        "llm_base_url": os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_LLM_BASE_URL,
        "llm_api_key": os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "",
        "llm_model": os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
        "llm_timeout": float(os.environ.get("LLM_TIMEOUT_SECONDS", "90")),
        "llm_max_retries": int(os.environ.get("LLM_MAX_RETRIES", "1")),
        "llm_max_tokens": int(os.environ.get("QA_LLM_MAX_TOKENS", "1200")),
        **DEFAULT_QA_OPTIONS,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def summarize_context(context: dict) -> dict:
    return {
        "query": context["query"],
        "keywords": context["keywords"],
        "vector_queries": context.get("vector_queries", []),
        "graph_counts": {
            "entities": len(context["graph"]["entities"]),
            "relations": len(context["graph"]["relations"]),
            "chunks": len(context["graph"]["chunk_ids"]),
        },
        "contexts": [
            {
                "citation_id": item.get("citation_id"),
                "retrieval": item.get("retrieval"),
                "score": item.get("score"),
                "chunk_id": item.get("chunk_id"),
                "title": item.get("title"),
                "year": item.get("year"),
                "evidence_level": item.get("evidence_level"),
                "source_type": item.get("source_type"),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
                "vector_query": item.get("vector_query"),
            }
            for item in context["contexts"]
        ],
        "relations": [
            {
                "graph_id": f"G{idx}",
                "source": row.get("source"),
                "source_type": row.get("source_type"),
                "relation": row.get("relation"),
                "target": row.get("target"),
                "target_type": row.get("target_type"),
                "support_count": row.get("support_count"),
                "confidence": row.get("confidence"),
                "qa_usage": row.get("qa_usage"),
            }
            for idx, row in enumerate(context["relations"][:20], 1)
        ],
    }


def answer_query(args, *, driver=None, embed_model=None, qdrant_client=None) -> dict:
    t0 = time.perf_counter()
    context = retrieve_context(args, driver=driver, embed_model=embed_model, qdrant_client=qdrant_client)
    retrieve_sec = time.perf_counter() - t0
    prompt_t0 = time.perf_counter()
    messages = build_prompt(context, args.max_chars_per_chunk)
    prompt_sec = time.perf_counter() - prompt_t0
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    result = {
        "query": context["query"],
        "dry_run": bool(args.dry_run),
        "context": summarize_context(context),
        "timing": {
            "retrieve_sec": round(retrieve_sec, 3),
            "prompt_build_sec": round(prompt_sec, 3),
            "prompt_chars": prompt_chars,
            "llm_sec": 0.0,
        },
    }
    if args.dry_run:
        result["prompt_preview"] = messages[-1]["content"]
        return result
    if not args.llm_api_key:
        raise RuntimeError("LLM API key is not set. Use dry_run or set LLM_API_KEY / OPENAI_API_KEY.")
    llm_t0 = time.perf_counter()
    result["answer"] = call_openai_compatible(
        model=args.llm_model,
        messages=messages,
        base_url=args.llm_base_url,
        api_key=args.llm_api_key,
        timeout_seconds=args.llm_timeout,
        max_retries=args.llm_max_retries,
        max_tokens=args.llm_max_tokens,
    )
    result["timing"]["llm_sec"] = round(time.perf_counter() - llm_t0, 3)
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    load_dotenv(ROOT / ".env")

    ap = argparse.ArgumentParser(description="KGRAG QA prototype")
    ap.add_argument("query")
    ap.add_argument("--keywords", nargs="*", default=[])
    ap.add_argument("--neo4j-url", default=os.environ.get("NEO4J_URL", NEO4J_DEFAULT_URL))
    ap.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", NEO4J_DEFAULT_USER))
    ap.add_argument("--neo4j-pass", default=os.environ.get("NEO4J_PASS", NEO4J_DEFAULT_PASS))
    ap.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", QDRANT_DEFAULT_URL))
    ap.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", DEFAULT_COLLECTION))
    ap.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL))
    ap.add_argument("--retrieval-k", type=int, default=20)
    ap.add_argument("--context-k", type=int, default=6)
    ap.add_argument("--relation-k", type=int, default=30)
    ap.add_argument("--relation-evidence-k", type=int, default=6)
    ap.add_argument("--graph-evidence-k", type=int, default=4)
    ap.add_argument("--graph-evidence-pool-k", type=int, default=30)
    ap.add_argument("--max-chars-per-chunk", type=int, default=900)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_LLM_BASE_URL)
    ap.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "")
    ap.add_argument("--llm-model", default=os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL)
    ap.add_argument("--llm-timeout", type=float, default=float(os.environ.get("LLM_TIMEOUT_SECONDS", "90")))
    ap.add_argument("--llm-max-retries", type=int, default=int(os.environ.get("LLM_MAX_RETRIES", "1")))
    ap.add_argument("--llm-max-tokens", type=int, default=int(os.environ.get("QA_LLM_MAX_TOKENS", "1200")))
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    result = answer_query(args)
    if result["dry_run"]:
        print(format_dry_run(
            {
                "query": result["query"],
                "keywords": result["context"]["keywords"],
                "graph": {
                    "entities": [None] * result["context"]["graph_counts"]["entities"],
                    "relations": [None] * result["context"]["graph_counts"]["relations"],
                    "chunk_ids": [None] * result["context"]["graph_counts"]["chunks"],
                },
                "contexts": result["context"]["contexts"],
            },
            [{"content": ""}, {"content": result["prompt_preview"]}],
        ))
        return 0
    print(result["answer"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
