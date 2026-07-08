#!/usr/bin/env python3
"""Hybrid retrieval: Neo4j subgraph + Qdrant vector search."""
from __future__ import annotations

import argparse
import os
import re

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient


NEO4J_DEFAULT_URL = 'bolt://localhost:7687'
NEO4J_DEFAULT_USER = 'neo4j'
NEO4J_DEFAULT_PASS = 'asd-kgrag-local'
QDRANT_DEFAULT_URL = 'http://localhost:6333'
DEFAULT_MODEL = 'BAAI/bge-small-zh-v1.5'
DEFAULT_COLLECTION = 'asd_kgrag_chunks'


GENERIC_KEYWORDS = {'asd', 'autism', '孤独症', '自闭症', '孤独症谱系障碍', '自闭症谱系障碍'}


def normalize_key(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def is_generic_keyword(keyword):
    return normalize_key(keyword) in GENERIC_KEYWORDS


def entity_match_score(entity):
    exact = 1 if entity.get('exact_match') else 0
    specific = 1 if any(not is_generic_keyword(kw) for kw in entity.get('matched_keywords', [])) else 0
    source_chunks = int(entity.get('source_chunk_count') or 0)
    source_docs = int(entity.get('source_doc_count') or 0)
    flags = set(entity.get('quality_flags') or [])
    penalty = 0
    if entity.get('is_isolated'):
        penalty += 20
    if 'single_chunk_entity' in flags:
        penalty += 10
    if entity.get('tool_category') in {'research_modality', 'digital_algorithm', 'generic_method'}:
        penalty += 4
    intent_bonus = 0
    matched = ''.join(entity.get('matched_keywords', [])).lower()
    entity_type = entity.get('type')
    if any(token in matched for token in ('干预', 'intervention', 'therapy', 'training', '训练', '治疗')):
        intent_bonus += 2 if entity_type == 'Intervention' else -2
    if any(token in matched for token in ('评估', '筛查', '诊断', '量表', '问卷', 'assessment', 'screening', 'diagnostic', 'checklist', 'scale', 'questionnaire')):
        intent_bonus += 2 if entity_type == 'AssessmentTool' else -1
    if any(token in matched for token in ('风险', 'risk', '早产', '围产', '围生')):
        intent_bonus += 1 if entity_type in {'Risk', 'AgeStage'} else -1
    return (
        specific,
        exact,
        intent_bonus,
        min(source_docs, 20),
        min(source_chunks, 100),
        -penalty,
        -len(entity.get('name') or ''),
    )


def graph_search(driver, keywords, max_hops=2):
    """Search Neo4j for entities matching keywords, expand subgraph, return related chunk IDs."""
    chunk_ids = set()
    entities_by_id = {}
    has_specific_keyword = any(not is_generic_keyword(kw) for kw in keywords)

    with driver.session() as session:
        # Fuzzy match entities by name/synonyms
        for kw in keywords:
            normalized_kw = normalize_key(kw)
            if not normalized_kw:
                continue
            result = session.run(
                'MATCH (e:Entity) '
                'WHERE toLower(e.name) CONTAINS toLower($kw) '
                'OR any(syn IN coalesce(e.synonyms, []) WHERE toLower(syn) CONTAINS toLower($kw)) '
                'RETURN e.entity_id AS eid, e.name AS name, e.type AS type, '
                '       e.source_chunk_count AS source_chunk_count, '
                '       e.source_doc_count AS source_doc_count, '
                '       e.quality_flags AS quality_flags, '
                '       e.is_isolated AS is_isolated, '
                '       e.tool_category AS tool_category, '
                '       coalesce(e.synonyms, []) AS synonyms '
                'LIMIT 80',
                kw=kw,
            )
            for rec in result:
                eid = rec['eid']
                entity = entities_by_id.setdefault(
                    eid,
                    {
                        'entity_id': eid,
                        'name': rec['name'],
                        'type': rec['type'],
                        'source_chunk_count': rec['source_chunk_count'] or 0,
                        'source_doc_count': rec['source_doc_count'] or 0,
                        'quality_flags': rec['quality_flags'] or [],
                        'is_isolated': bool(rec['is_isolated']),
                        'tool_category': rec['tool_category'] or '',
                        'matched_keywords': [],
                        'exact_match': False,
                    },
                )
                entity['matched_keywords'].append(kw)
                aliases = [rec['name'], *(rec['synonyms'] or [])]
                if any(normalize_key(alias) == normalized_kw for alias in aliases):
                    entity['exact_match'] = True

        entities_found = list(entities_by_id.values())
        if has_specific_keyword:
            specific_entities = [
                entity
                for entity in entities_found
                if any(not is_generic_keyword(kw) for kw in entity.get('matched_keywords', []))
            ]
            if specific_entities:
                entities_found = specific_entities
        entities_found.sort(key=entity_match_score, reverse=True)
        entities_found = entities_found[:60]

        if not entities_found:
            return {'entities': [], 'chunk_ids': [], 'relations': []}

        # Expand 1-hop from matched entities
        entity_ids = [e['entity_id'] for e in entities_found]
        result = session.run(
            'MATCH (e:Entity)-[r]-(neighbor) '
            'WHERE e.entity_id IN $eids '
            'RETURN e.entity_id AS src_id, type(r) AS rel_type, '
            'neighbor.entity_id AS neighbor_id, neighbor.name AS neighbor_name, '
            'neighbor.type AS neighbor_type '
            'LIMIT 100',
            eids=entity_ids,
        )
        relations = []
        for rec in result:
            relations.append({
                'src_id': rec['src_id'],
                'rel_type': rec['rel_type'],
                'neighbor_id': rec['neighbor_id'],
                'neighbor_name': rec['neighbor_name'],
                'neighbor_type': rec['neighbor_type'],
            })

        # Get chunks linked to matched entities and neighbors
        all_eids = list(set(entity_ids + [r['neighbor_id'] for r in relations if r['neighbor_id']]))
        if all_eids:
            result = session.run(
                'MATCH (e:Entity)-[:SUPPORTED_BY]->(ev:Evidence)-[:FROM_CHUNK|FROM]->(c:Chunk) '
                'WHERE e.entity_id IN $eids '
                'RETURN DISTINCT c.chunk_id AS chunk_id LIMIT 200',
                eids=all_eids,
            )
            for rec in result:
                if rec['chunk_id']:
                    chunk_ids.add(rec['chunk_id'])

        # Also try: matched Entity directly connected to Chunk
        result = session.run(
            'MATCH (e:Entity)-[:FROM_CHUNK|FROM]->(c:Chunk) '
            'WHERE e.entity_id IN $eids '
            'RETURN DISTINCT c.chunk_id AS chunk_id LIMIT 200',
            eids=entity_ids,
        )
        for rec in result:
            if rec['chunk_id']:
                chunk_ids.add(rec['chunk_id'])

        # Broader path: entity --> related entity via any rel --> Evidence --> Chunk
        result = session.run(
            'MATCH (e:Entity)-[r1]-(neighbor:Entity)-[:SUPPORTED_BY]->(ev:Evidence)-[:FROM_CHUNK|FROM]->(c:Chunk) '
            'WHERE e.entity_id IN $eids AND neighbor.entity_id IS NOT NULL '
            'RETURN DISTINCT c.chunk_id AS chunk_id LIMIT 300',
            eids=entity_ids,
        )
        for rec in result:
            if rec['chunk_id']:
                chunk_ids.add(rec['chunk_id'])

    return {
        'entities': entities_found[:20],
        'relations': relations[:50],
        'chunk_ids': list(chunk_ids),
    }


def vector_search(client, model, query, collection, top_k=20):
    """Search Qdrant for semantically similar chunks."""
    query_vec = model.encode([query])[0].tolist()
    results = client.query_points(
        collection_name=collection,
        query=query_vec,
        limit=top_k,
    )
    hits = []
    for point in results.points:
        p = point.payload
        hits.append({
            'chunk_id': p.get('chunk_id', ''),
            'score': point.score,
            'doc_id': p.get('doc_id', ''),
            'title': p.get('title', ''),
            'year': p.get('year'),
            'evidence_level': p.get('evidence_level', ''),
            'source_type': p.get('source_type', ''),
        })
    return hits


def merge_results(graph_chunk_ids, vector_hits):
    """Merge graph and vector results. Boost chunks that appear in both."""
    graph_set = set(graph_chunk_ids)
    for hit in vector_hits:
        if hit['chunk_id'] in graph_set:
            hit['in_graph'] = True
            hit['merged_score'] = hit['score'] + 0.15
        else:
            hit['in_graph'] = False
            hit['merged_score'] = hit['score']

    evidence_weight = {'S': 0.1, 'A': 0.05, 'B': 0.0, 'C': -0.02, 'D': -0.05}
    for hit in vector_hits:
        hit['merged_score'] += evidence_weight.get(hit.get('evidence_level', ''), 0.0)

    vector_hits.sort(key=lambda h: h['merged_score'], reverse=True)
    return vector_hits


def main():
    ap = argparse.ArgumentParser(description='Hybrid KGRAG retrieval')
    ap.add_argument('query', help='Search query')
    ap.add_argument('--keywords', nargs='*', default=[], help='Explicit entity keywords')
    ap.add_argument('--neo4j-url', default=os.environ.get('NEO4J_URL', NEO4J_DEFAULT_URL))
    ap.add_argument('--neo4j-user', default=os.environ.get('NEO4J_USER', NEO4J_DEFAULT_USER))
    ap.add_argument('--neo4j-pass', default=os.environ.get('NEO4J_PASS', NEO4J_DEFAULT_PASS))
    ap.add_argument('--qdrant-url', default=os.environ.get('QDRANT_URL', QDRANT_DEFAULT_URL))
    ap.add_argument('--collection', default=DEFAULT_COLLECTION)
    ap.add_argument('--model', default=os.environ.get('EMBEDDING_MODEL', DEFAULT_MODEL))
    ap.add_argument('--top-k', type=int, default=20)
    ap.add_argument('--graph-only', action='store_true')
    ap.add_argument('--vector-only', action='store_true')
    args = ap.parse_args()

    if args.keywords:
        keywords = args.keywords
    else:
        # Auto-split query into shorter fragments for graph entity matching
        import re
        # Split on spaces, punctuation, and CJK character boundaries
        tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]*|[一-鿿]{2,}', args.query)
        keywords = list(set(tokens)) if tokens else [args.query]

    # Graph search
    graph_result = {'entities': [], 'relations': [], 'chunk_ids': []}
    if not args.vector_only:
        driver = GraphDatabase.driver(args.neo4j_url, auth=(args.neo4j_user, args.neo4j_pass))
        try:
            graph_result = graph_search(driver, keywords)
            print(f'graph: {len(graph_result["entities"])} entities, {len(graph_result["relations"])} relations, {len(graph_result["chunk_ids"])} chunks')
        finally:
            driver.close()
    else:
        print('graph: skipped (vector-only mode)')

    # Vector search
    vector_hits = []
    if not args.graph_only:
        model = SentenceTransformer(args.model)
        client = QdrantClient(url=args.qdrant_url)
        vector_hits = vector_search(client, model, args.query, args.collection, args.top_k)
        print(f'vector: {len(vector_hits)} hits')
    else:
        print('vector: skipped (graph-only mode)')

    # Merge
    merged = merge_results(graph_result['chunk_ids'], vector_hits) if vector_hits else []

    print(f'\n=== Query: {args.query} ===')
    print('Graph entities found:')
    for e in graph_result['entities'][:10]:
        print(f'  {e["name"]} ({e["type"]})')
    print('\nGraph relations:')
    for r in graph_result['relations'][:10]:
        print(f'  [{r["src_id"]}]-{r["rel_type"]}->{r["neighbor_name"]} ({r["neighbor_type"]})')

    print(f'\nMerged results (top {min(len(merged), 10)}):')
    for i, h in enumerate(merged[:10], 1):
        graph_marker = '[G+V]' if h.get('in_graph') else '[V]  '
        print(f'  {i}. {graph_marker} score={h["merged_score"]:.4f} evid={h["evidence_level"]} {h["title"][:60]}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
