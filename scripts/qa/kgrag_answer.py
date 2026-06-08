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
    return score, -float(row.get("relation_rank") or 0)


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


def retrieve_context(args) -> dict:
    keywords = args.keywords if args.keywords else auto_keywords(args.query)
    driver = GraphDatabase.driver(args.neo4j_url, auth=(args.neo4j_user, args.neo4j_pass))
    try:
        graph_result = graph_search(driver, keywords)
        model = SentenceTransformer(args.model)
        client = QdrantClient(url=args.qdrant_url)
        vector_hits = vector_search(client, model, args.query, args.collection, args.retrieval_k)
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
            if specific_graph_evidence:
                graph_evidence_pool = specific_graph_evidence
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
        driver.close()

    return {
        "query": args.query,
        "keywords": keywords,
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


def trim_text(text: str, max_chars: int, keywords: list[str] | None = None) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    keywords = keywords or []
    lowered = text.lower()
    hit_positions = [
        lowered.find(keyword.lower())
        for keyword in keywords
        if keyword and lowered.find(keyword.lower()) >= 0
    ]
    if hit_positions and len(text) > max_chars:
        center = min(hit_positions)
        start = max(0, center - max_chars // 3)
        end = min(len(text), start + max_chars)
        snippet = text[start:end]
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{snippet}{suffix}"
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


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


def answer_query(args) -> dict:
    context = retrieve_context(args)
    messages = build_prompt(context, args.max_chars_per_chunk)
    result = {
        "query": context["query"],
        "dry_run": bool(args.dry_run),
        "context": summarize_context(context),
    }
    if args.dry_run:
        result["prompt_preview"] = messages[-1]["content"]
        return result
    if not args.llm_api_key:
        raise RuntimeError("LLM API key is not set. Use dry_run or set LLM_API_KEY / OPENAI_API_KEY.")
    result["answer"] = call_openai_compatible(
        model=args.llm_model,
        messages=messages,
        base_url=args.llm_base_url,
        api_key=args.llm_api_key,
        timeout_seconds=args.llm_timeout,
        max_retries=args.llm_max_retries,
        max_tokens=args.llm_max_tokens,
    )
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
