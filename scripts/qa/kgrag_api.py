#!/usr/bin/env python3
"""FastAPI server for the KGRAG QA pipeline."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
QA_EVAL_DIR = ROOT / "data" / "qa_eval"
sys.path.insert(0, str(ROOT / "scripts" / "qa"))

from kgrag_answer import (  # noqa: E402
    answer_query,
    default_namespace,
    load_dotenv,
    stream_answer_query_events,
)
from agent_tools import run_toolized_agent  # noqa: E402
from agent_trace import AgentTrace  # noqa: E402

logger = logging.getLogger("kgrag-api")


# ---------------------------------------------------------------------------
# Auth utilities
# ---------------------------------------------------------------------------

def _get_password() -> str:
    pw = os.environ.get("DASHBOARD_PASSWORD") or ""
    if not pw:
        pw = secrets.token_urlsafe(16)
        os.environ["DASHBOARD_PASSWORD"] = pw
    return pw


def _sign(payload: str) -> str:
    return hmac.new(
        _get_password().encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_token() -> tuple[str, datetime]:
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    raw = f"{exp.timestamp()}:{secrets.token_hex(8)}"
    sig = _sign(raw)
    return f"{raw}:{sig}", exp


def verify_token(token: str) -> bool:
    try:
        parts = token.rsplit(":", 1)
        if len(parts) != 2:
            return False
        raw, sig = parts
        expected = _sign(raw)
        if not hmac.compare_digest(sig, expected):
            return False
        ts = float(raw.split(":")[0])
        return datetime.now(timezone.utc).timestamp() < ts
    except (ValueError, IndexError, TypeError):
        return False


async def auth_dep(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token or not verify_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")


AuthDep = Annotated[None, Depends(auth_dep)]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    query: str
    keywords: list[str] = []
    dry_run: bool = False
    agent_mode: bool = False
    include_trace: bool = False
    retrieval_k: int = Field(default=20, ge=1, le=100)
    context_k: int = Field(default=6, ge=1, le=30)
    relation_k: int = Field(default=30, ge=1, le=100)
    relation_evidence_k: int = Field(default=6, ge=1, le=30)
    graph_evidence_k: int = Field(default=4, ge=1, le=30)
    graph_evidence_pool_k: int = Field(default=30, ge=1, le=100)
    max_chars_per_chunk: int = Field(default=900, ge=100, le=5000)


class HealthResponse(BaseModel):
    status: str
    service: str
    time: int


# Auth models

class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str


# Dashboard query models

class PaginationParams:
    def __init__(self, page: int = 1, page_size: int = 20):
        self.page = page
        self.page_size = min(page_size, 100)


class EntitiesFilter:
    def __init__(self, search: str = "", type: str = "", page: int = 1, page_size: int = 20):
        self.search = search
        self.type = type
        self.page = page
        self.page_size = min(page_size, 100)


class RelationsFilter:
    def __init__(self, entity: str = "", page: int = 1, page_size: int = 20):
        self.entity = entity
        self.page = page
        self.page_size = min(page_size, 100)


class ChunksFilter:
    def __init__(self, doc_id: str = "", evidence_level: str = "", search: str = "", page: int = 1, page_size: int = 20):
        self.doc_id = doc_id
        self.evidence_level = evidence_level
        self.search = search
        self.page = page
        self.page_size = min(page_size, 100)


# Phase 2 models

class ActiveModelModel(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: int | None = None
    max_tokens: int | None = None
    max_retries: int | None = None


class UpdateSettingsRequest(BaseModel):
    active_model: ActiveModelModel


class EvalModelModel(BaseModel):
    name: str
    base_url: str = ""
    api_key: str = ""
    timeout: int = 90
    max_tokens: int = 1200
    max_retries: int = 1
    enabled: bool = True


class EvalQuestionModel(BaseModel):
    id: str
    category: str = "general"
    query: str
    keywords: list[str] = []
    expect_graph_terms: list[str] = []
    requires_guardrail: bool = False
    requires_research_boundary: bool = False


# ---------------------------------------------------------------------------
# Lifespan: create shared connections once, reuse across requests
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    from neo4j import GraphDatabase
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer

    load_dotenv(ROOT / ".env")
    ns = default_namespace()

    logger.info("Loading embedding model: %s", ns.model)
    app.state.embed_model = SentenceTransformer(ns.model)

    logger.info("Connecting to Neo4j: %s", ns.neo4j_url)
    app.state.neo4j_driver = GraphDatabase.driver(
        ns.neo4j_url, auth=(ns.neo4j_user, ns.neo4j_pass)
    )

    logger.info("Connecting to Qdrant: %s", ns.qdrant_url)
    app.state.qdrant_client = QdrantClient(url=ns.qdrant_url)

    logger.info("KGRAG QA API ready")
    yield

    app.state.neo4j_driver.close()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ASD-KGRAG QA",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", service="kgrag-qa", time=int(time.time()))


@app.post("/ask")
async def ask(body: AskRequest, request: Request):
    started_at = time.perf_counter()
    ns = default_namespace(
        query=body.query,
        keywords=body.keywords,
        dry_run=body.dry_run,
        retrieval_k=body.retrieval_k,
        context_k=body.context_k,
        relation_k=body.relation_k,
        relation_evidence_k=body.relation_evidence_k,
        graph_evidence_k=body.graph_evidence_k,
        graph_evidence_pool_k=body.graph_evidence_pool_k,
        max_chars_per_chunk=body.max_chars_per_chunk,
    )
    from qa_settings import apply_active_model_to_ns

    apply_active_model_to_ns(ns)
    try:
        if body.agent_mode:
            trace = AgentTrace(query=body.query)
            result = await run_in_threadpool(
                run_toolized_agent,
                ns,
                driver=request.app.state.neo4j_driver,
                embed_model=request.app.state.embed_model,
                qdrant_client=request.app.state.qdrant_client,
                trace=trace,
            )
            if body.include_trace:
                result["agent_trace"] = trace.to_dict()
        else:
            result = await run_in_threadpool(
                answer_query,
                ns,
                driver=request.app.state.neo4j_driver,
                embed_model=request.app.state.embed_model,
                qdrant_client=request.app.state.qdrant_client,
            )
    except Exception as exc:
        logger.exception("qa request failed")
        return JSONResponse(
            status_code=500,
            content={"error": "qa_failed", "detail": str(exc)},
        )
    if isinstance(result, dict):
        result.setdefault("timing", {})["api_total_sec"] = round(time.perf_counter() - started_at, 3)
    return result


def _sse_event(payload: dict) -> str:
    event_type = payload.get("type", "message")
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


@app.post("/ask/stream")
async def ask_stream(body: AskRequest, request: Request):
    ns = default_namespace(
        query=body.query,
        keywords=body.keywords,
        dry_run=body.dry_run,
        retrieval_k=body.retrieval_k,
        context_k=body.context_k,
        relation_k=body.relation_k,
        relation_evidence_k=body.relation_evidence_k,
        graph_evidence_k=body.graph_evidence_k,
        graph_evidence_pool_k=body.graph_evidence_pool_k,
        max_chars_per_chunk=body.max_chars_per_chunk,
    )
    from qa_settings import apply_active_model_to_ns

    apply_active_model_to_ns(ns)

    def event_stream():
        try:
            if body.agent_mode:
                yield _sse_event(
                    {
                        "type": "error",
                        "error": "unsupported_stream_mode",
                        "detail": "Streaming is currently implemented for the standard KGRAG answer path.",
                    }
                )
                return
            for event in stream_answer_query_events(
                ns,
                driver=request.app.state.neo4j_driver,
                embed_model=request.app.state.embed_model,
                qdrant_client=request.app.state.qdrant_client,
            ):
                yield _sse_event(event)
        except Exception as exc:
            logger.exception("qa stream failed")
            yield _sse_event({"type": "error", "error": "qa_failed", "detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.post("/auth/login")
async def login(body: LoginRequest):
    if not hmac.compare_digest(body.password, _get_password()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="wrong password")
    token, exp = create_token()
    return LoginResponse(token=token, expires_at=exp.isoformat())


@app.get("/auth/verify")
async def verify(_auth: AuthDep):
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard routes (authenticated)
# ---------------------------------------------------------------------------

@app.get("/dashboard/stats")
async def dashboard_stats(_auth: AuthDep, request: Request):
    from dashboard_queries import get_stats

    return get_stats(request.app.state.neo4j_driver)


@app.get("/dashboard/entities")
async def dashboard_entities(_auth: AuthDep, request: Request, search: str = "", type: str = "", page: int = 1, page_size: int = 20):
    from dashboard_queries import list_entities

    return list_entities(
        request.app.state.neo4j_driver,
        page=page,
        page_size=page_size,
        search=search,
        type_filter=type,
    )


@app.get("/dashboard/relations")
async def dashboard_relations(_auth: AuthDep, request: Request, entity: str = "", page: int = 1, page_size: int = 20):
    from dashboard_queries import list_relations

    return list_relations(
        request.app.state.neo4j_driver,
        page=page,
        page_size=page_size,
        entity_filter=entity,
    )


@app.get("/dashboard/chunks")
async def dashboard_chunks(_auth: AuthDep, request: Request, doc_id: str = "", evidence_level: str = "", search: str = "", page: int = 1, page_size: int = 20):
    from dashboard_queries import list_chunks

    return list_chunks(
        request.app.state.neo4j_driver,
        page=page,
        page_size=page_size,
        doc_id=doc_id,
        evidence_level=evidence_level,
        search=search,
    )


@app.get("/dashboard/graph-data")
async def dashboard_graph_data(_auth: AuthDep, request: Request, limit_entities: int = 50, limit_relations: int = 200):
    from dashboard_queries import get_graph_data

    return get_graph_data(
        request.app.state.neo4j_driver,
        limit_entities=limit_entities,
        limit_relations=limit_relations,
    )


# ---------------------------------------------------------------------------
# Phase 2: Settings & Evaluation routes
# ---------------------------------------------------------------------------

@app.get("/dashboard/settings")
async def get_settings(_auth: AuthDep):
    from qa_settings import get_settings

    return get_settings()


@app.put("/dashboard/settings")
async def put_settings(_auth: AuthDep, body: UpdateSettingsRequest):
    from qa_settings import update_active_model

    return update_active_model(body.active_model.model_dump(exclude_none=True))


@app.get("/dashboard/eval-models")
async def get_eval_models(_auth: AuthDep):
    from qa_settings import get_eval_models

    return get_eval_models()


@app.post("/dashboard/eval-models")
async def add_eval_model(_auth: AuthDep, body: EvalModelModel):
    from qa_settings import add_eval_model

    return add_eval_model(body.model_dump())


@app.patch("/dashboard/eval-models/{index}")
async def patch_eval_model(_auth: AuthDep, index: int, body: EvalModelModel):
    from qa_settings import update_eval_model

    return update_eval_model(index, body.model_dump(exclude_unset=True))


@app.delete("/dashboard/eval-models/{index}")
async def delete_eval_model(_auth: AuthDep, index: int):
    from qa_settings import delete_eval_model

    return delete_eval_model(index)


@app.get("/dashboard/eval-questions")
async def get_eval_questions(_auth: AuthDep):
    from kgrag_answer import load_dotenv
    from evaluate_qa import read_jsonl

    load_dotenv(ROOT / ".env")
    return read_jsonl(ROOT / "scripts" / "qa" / "eval_questions.jsonl")


@app.post("/dashboard/eval-questions")
async def add_eval_question(_auth: AuthDep, body: EvalQuestionModel):
    from kgrag_answer import load_dotenv
    from evaluate_qa import read_jsonl, write_jsonl

    load_dotenv(ROOT / ".env")
    path = ROOT / "scripts" / "qa" / "eval_questions.jsonl"
    questions = read_jsonl(path)
    questions.append(body.model_dump())
    write_jsonl(path, questions)
    return questions


@app.patch("/dashboard/eval-questions/{question_id}")
async def patch_eval_question(_auth: AuthDep, question_id: str, body: EvalQuestionModel):
    from kgrag_answer import load_dotenv
    from evaluate_qa import read_jsonl, write_jsonl

    load_dotenv(ROOT / ".env")
    path = ROOT / "scripts" / "qa" / "eval_questions.jsonl"
    questions = read_jsonl(path)
    for q in questions:
        if q.get("id") == question_id:
            q.update(body.model_dump(exclude_unset=True))
            break
    write_jsonl(path, questions)
    return questions


@app.delete("/dashboard/eval-questions/{question_id}")
async def delete_eval_question(_auth: AuthDep, question_id: str):
    from kgrag_answer import load_dotenv
    from evaluate_qa import read_jsonl, write_jsonl

    load_dotenv(ROOT / ".env")
    path = ROOT / "scripts" / "qa" / "eval_questions.jsonl"
    questions = read_jsonl(path)
    questions = [q for q in questions if q.get("id") != question_id]
    write_jsonl(path, questions)
    return questions


@app.post("/dashboard/eval/run")
async def trigger_eval_run(_auth: AuthDep, request: Request):
    from qa_settings import get_eval_models
    from eval_runner import run_eval

    models = get_eval_models()
    if not models:
        raise HTTPException(status_code=400, detail="No eval models configured.")

    results = run_eval(
        models=models,
        dry_run=False,
        driver=request.app.state.neo4j_driver,
        embed_model=request.app.state.embed_model,
        qdrant_client=request.app.state.qdrant_client,
    )
    return {"timestamp": time.strftime("%Y%m%d_%H%M%S"), "models": results}


@app.get("/dashboard/eval/runs")
async def get_eval_runs(_auth: AuthDep):
    import json
    base = QA_EVAL_DIR
    print(f"DEBUG get_eval_runs base={base} exists={base.exists()}", flush=True)
    if not base.exists():
        return []
    entries = []
    for child in sorted(base.iterdir(), reverse=True)[:50]:
        if child.is_dir():
            summary = {}
            summary_path = child / "summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            entries.append({
                    "run_id": child.name,
                    "timestamp": child.name[:15],
                    "total": summary.get("total", 0),
                    "ok": summary.get("ok", 0),
                    "ok_rate": summary.get("ok_rate", 0),
                })
    return entries


@app.get("/dashboard/eval/runs/{run_id}")
async def get_eval_run_detail(_auth: AuthDep, run_id: str):
    import json
    base = QA_EVAL_DIR / run_id
    if not base.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    results_path = base / "results.jsonl"
    summary_path = base / "summary.json"
    results = []
    if results_path.exists():
        from evaluate_qa import read_jsonl
        results = read_jsonl(results_path)
    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"run_id": run_id, "summary": summary, "results": results}


# ---------------------------------------------------------------------------
# Student return routes
# ---------------------------------------------------------------------------


@app.post("/dashboard/returns/upload")
async def upload_return(_auth: AuthDep, file: UploadFile = File(...)):
    from return_store import store_return_file, ValidationError

    try:
        content = await file.read()
        result = store_return_file(file.filename or "unknown.csv", content)
        return result
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("return upload failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/dashboard/returns")
async def list_returns(_auth: AuthDep):
    from return_store import list_returns

    return list_returns()


@app.delete("/dashboard/returns/{filename:path}")
async def delete_return(_auth: AuthDep, filename: str):
    from return_store import delete_return

    if delete_return(filename):
        return {"deleted": filename}
    raise HTTPException(status_code=404, detail="File not found")


# ---------------------------------------------------------------------------
# Alias routes
# ---------------------------------------------------------------------------


@app.get("/dashboard/aliases")
async def get_aliases(_auth: AuthDep):
    from return_store import read_alias_map

    return read_alias_map()


@app.put("/dashboard/aliases")
async def put_aliases(_auth: AuthDep, body: dict):
    from return_store import write_alias_map

    return write_alias_map(body)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="Serve KGRAG QA over HTTP (FastAPI).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
