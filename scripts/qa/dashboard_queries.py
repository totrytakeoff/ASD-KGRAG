#!/usr/bin/env python3
"""Neo4j queries for the dashboard — stats, entities, relations, chunks."""

from __future__ import annotations

from typing import Any


def get_stats(driver) -> dict:
    """Return high-level graph statistics."""
    queries = {
        "entity_count": "MATCH (e:Entity) RETURN count(e) AS cnt",
        "entity_type_distribution": (
            "MATCH (e:Entity) RETURN e.type AS type, count(*) AS cnt ORDER BY cnt DESC"
        ),
        "relation_count": "MATCH ()-[r]->() RETURN count(r) AS cnt",
        "chunk_count": "MATCH (c:Chunk) RETURN count(c) AS cnt",
        "evidence_count": "MATCH (e:Evidence) RETURN count(e) AS cnt",
        "evidence_level_distribution": (
            "MATCH (c:Chunk) RETURN c.evidence_level AS level, count(*) AS cnt ORDER BY cnt DESC"
        ),
        "source_type_distribution": (
            "MATCH (c:Chunk) RETURN c.source_type AS source, count(*) AS cnt ORDER BY cnt DESC"
        ),
    }
    result = {}
    with driver.session() as session:
        for key, cypher in queries.items():
            rows = list(session.run(cypher))
            if key in ("entity_count", "relation_count", "chunk_count", "evidence_count"):
                result[key] = rows[0]["cnt"] if rows else 0
            else:
                name_key = {"entity_type_distribution": "type", "evidence_level_distribution": "level", "source_type_distribution": "source"}.get(key, "type")
                result[key] = [{"name": r[name_key], "count": r["cnt"]} for r in rows]
    return result


def list_entities(driver, *, page: int = 1, page_size: int = 20, search: str = "", type_filter: str = "") -> dict:
    """Paginated entity list with optional search and type filter."""
    skip = (page - 1) * page_size
    conditions = []
    params: dict[str, Any] = {}
    if search:
        conditions.append("e.name CONTAINS $search")
        params["search"] = search
    if type_filter:
        conditions.append("e.type = $type_filter")
        params["type_filter"] = type_filter
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    with driver.session() as session:
        count_row = list(session.run(f"MATCH (e:Entity) {where_clause} RETURN count(e) AS cnt", params))
        total = count_row[0]["cnt"] if count_row else 0
        rows = list(session.run(
            f"MATCH (e:Entity) {where_clause} RETURN e.entity_id AS entity_id, "
            "e.name AS name, e.type AS type, e.names AS names, e.synonyms AS synonyms "
            "ORDER BY e.name SKIP $skip LIMIT $limit",
            {**params, "skip": skip, "limit": page_size},
        ))
        items = []
        for r in rows:
            names = r.get("names")
            if isinstance(names, str):
                names = [x.strip() for x in names.split(";") if x.strip()]
            synonyms = r.get("synonyms")
            if isinstance(synonyms, str):
                synonyms = [x.strip() for x in synonyms.split(";") if x.strip()]
            items.append({
                "entity_id": r["entity_id"],
                "name": r["name"],
                "type": r["type"],
                "names": names or [],
                "synonyms": synonyms or [],
            })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def list_relations(driver, *, page: int = 1, page_size: int = 20, entity_filter: str = "") -> dict:
    """Paginated relation list, optionally filtered by source or target entity name."""
    skip = (page - 1) * page_size
    condition = ""
    params: dict[str, Any] = {"skip": skip, "limit": page_size}
    if entity_filter:
        condition = "WHERE a.name CONTAINS $entity_filter OR b.name CONTAINS $entity_filter"
        params["entity_filter"] = entity_filter
    with driver.session() as session:
        count_row = list(session.run(
            f"MATCH (a:Entity)-[r]->(b:Entity) {condition} RETURN count(r) AS cnt", params
        ))
        total = count_row[0]["cnt"] if count_row else 0
        rows = list(session.run(
            f"MATCH (a:Entity)-[r]->(b:Entity) {condition} "
            "RETURN a.name AS source, a.type AS source_type, "
            "type(r) AS relation, "
            "b.name AS target, b.type AS target_type, "
            "r.support_count AS support_count, r.confidence AS confidence, "
            "r.qa_usage AS qa_usage "
            "ORDER BY r.support_count DESC SKIP $skip LIMIT $limit",
            params,
        ))
        items = []
        for r in rows:
            items.append({
                "source": r["source"],
                "source_type": r["source_type"],
                "relation": r["relation"],
                "target": r["target"],
                "target_type": r["target_type"],
                "support_count": r.get("support_count"),
                "confidence": r.get("confidence"),
                "qa_usage": r.get("qa_usage"),
            })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def list_chunks(driver, *, page: int = 1, page_size: int = 20, doc_id: str = "", evidence_level: str = "", search: str = "") -> dict:
    """Paginated chunk list with optional filters and text preview."""
    skip = (page - 1) * page_size
    conditions = []
    params: dict[str, Any] = {}
    if doc_id:
        conditions.append("c.doc_id CONTAINS $doc_id")
        params["doc_id"] = doc_id
    if evidence_level:
        conditions.append("c.evidence_level = $evidence_level")
        params["evidence_level"] = evidence_level
    if search:
        conditions.append("c.text CONTAINS $search")
        params["search"] = search
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    with driver.session() as session:
        count_row = list(session.run(f"MATCH (c:Chunk) {where_clause} RETURN count(c) AS cnt", params))
        total = count_row[0]["cnt"] if count_row else 0
        rows = list(session.run(
            f"MATCH (c:Chunk) {where_clause} RETURN "
            "c.chunk_id AS chunk_id, c.doc_id AS doc_id, c.title AS title, "
            "c.year AS year, c.evidence_level AS evidence_level, "
            "c.source_type AS source_type, c.page_start AS page_start, "
            "c.page_end AS page_end, c.text AS text "
            "ORDER BY c.title SKIP $skip LIMIT $limit",
            {**params, "skip": skip, "limit": page_size},
        ))
        items = []
        for r in rows:
            text = r.get("text") or ""
            preview = text[:300] + ("..." if len(text) > 300 else "")
            items.append({
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "title": r["title"],
                "year": r.get("year"),
                "evidence_level": r["evidence_level"],
                "source_type": r["source_type"],
                "page_start": r.get("page_start"),
                "page_end": r.get("page_end"),
                "text_preview": preview,
                "text_length": len(text),
            })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_graph_data(driver, *, limit_entities: int = 50, limit_relations: int = 200) -> dict:
    """Return nodes and edges for graph visualization (top connected entities)."""
    with driver.session() as session:
        entity_rows = list(session.run(
            "MATCH (e:Entity) OPTIONAL MATCH (e)-[r]-() "
            "WITH e, count(r) AS degree ORDER BY degree DESC LIMIT $limit "
            "RETURN e.entity_id AS entity_id, e.name AS name, e.type AS type, degree",
            {"limit": limit_entities},
        ))
        entity_ids = [r["entity_id"] for r in entity_rows if r["entity_id"]]
        nodes = [
            {"id": r["entity_id"], "name": r["name"], "type": r["type"], "degree": r["degree"]}
            for r in entity_rows if r["entity_id"]
        ]
        rel_rows = list(session.run(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE a.entity_id IN $ids AND b.entity_id IN $ids "
            "RETURN a.name AS source, a.entity_id AS source_id, "
            "b.name AS target, b.entity_id AS target_id, "
            "type(r) AS relation, r.support_count AS support_count, "
            "r.confidence AS confidence, r.qa_usage AS qa_usage "
            "ORDER BY r.support_count DESC LIMIT $limit",
            {"ids": entity_ids, "limit": limit_relations},
        ))
        edges = [
            {
                "source_id": r["source_id"], "source": r["source"],
                "target_id": r["target_id"], "target": r["target"],
                "relation": r["relation"],
                "support_count": r.get("support_count"),
                "confidence": r.get("confidence"),
                "qa_usage": r.get("qa_usage"),
            }
            for r in rel_rows
        ]
    return {"nodes": nodes, "edges": edges}
