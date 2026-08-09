import time
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from app.config import settings
from app.core.logger import setup_logging
from app.core.vllm_client import vllm_client
from app.core.redis_cache import semantic_cache
from app.core.guardrails import guardrails
from app.models.schemas import IngestionRequest, QueryRequest, CollectionStats
from app.services.ingestion import DocumentIngestionService
from app.services.retriever import retriever
from app.services.generator import rag_generator
from app.services.embeddings import embedding_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup Events
    setup_logging()
    logger.info("Starting Enterprise vLLM & Hybrid RAG System...")

    # Initialize Cache (non-fatal if Redis is unavailable)
    try:
        await semantic_cache.connect()
    except Exception as e:
        logger.warning(f"Redis cache unavailable at startup: {e}")

    # Initialize Qdrant Collection (non-fatal if Qdrant is unavailable)
    try:
        ingestion_service = DocumentIngestionService()
        await ingestion_service.initialize_collection()
    except Exception as e:
        logger.warning(f"Qdrant unavailable at startup: {e}")

    # Check vLLM Health (non-fatal — demo mode handles this)
    vllm_healthy = await vllm_client.check_health()
    if not vllm_healthy:
        logger.warning("vLLM Engine is not reachable at startup. DEMO_MODE will handle queries.")

    yield

    # Shutdown Events
    logger.info("Shutting down services...")
    try:
        await semantic_cache.disconnect()
    except Exception:
        pass
    try:
        await vllm_client.close()
    except Exception:
        pass


app = FastAPI(
    title="Enterprise vLLM RAG API",
    description="High-performance Self-Hosted RAG Backend — Demo-Ready",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next: Any) -> Any:
    start_time = time.time()
    response = await call_next(request)
    process_time_ms = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-ms"] = f"{process_time_ms:.2f}"
    return response


@app.get("/health")
async def health_check() -> Dict[str, str]:
    redis_status = "ok" if semantic_cache.redis_client else "disconnected"
    vllm_status = "ok" if await vllm_client.check_health() else "unreachable"

    return {
        "status": "healthy",
        "api": "ok",
        "redis": redis_status,
        "vllm": vllm_status,
        "demo_mode": str(settings.demo_mode).lower(),
    }


@app.get("/api/v1/stats", response_model=CollectionStats)
async def get_collection_stats() -> CollectionStats:
    """Return stats about the Qdrant vector collection (document count, status)."""
    try:
        from qdrant_client import AsyncQdrantClient
        qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        info = await qdrant.get_collection("enterprise_knowledge")
        return CollectionStats(
            collection_name="enterprise_knowledge",
            total_points=info.points_count or 0,
            status=str(info.status),
        )
    except Exception as e:
        logger.warning(f"Could not fetch collection stats: {e}")
        return CollectionStats(
            collection_name="enterprise_knowledge",
            total_points=0,
            status="unavailable",
        )


@app.post("/api/v1/ingest")
async def ingest_documents(request: IngestionRequest) -> Any:
    ingestion_service = DocumentIngestionService()
    try:
        response = await ingestion_service.process_ingestion(request)
        return response
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/query")
async def query_sync(request: QueryRequest) -> Any:
    start_time = time.time()

    # 1. Guardrails
    sanitized_query = await guardrails.sanitize_input(request.user_query)
    await guardrails.check_prompt_injection(sanitized_query)
    request.user_query = sanitized_query

    # 2. Cache Check
    dense_embeds, _ = await embedding_engine.generate_embeddings_batch(
        [request.user_query], batch_size=1
    )
    query_embed = dense_embeds[0]

    cached_res = await semantic_cache.get_cached_response(request.user_query, query_embed)
    if cached_res:
        latency = (time.time() - start_time) * 1000
        cached_res["latency_ms"] = latency
        cached_res["cache_hit"] = True
        return cached_res

    # 3. Retrieval
    query_response = await retriever.search(request)

    # 4. Generation
    gen_result = await rag_generator.generate_response(
        request.user_query, query_response.retrieved_chunks
    )

    # 5. Output Audit
    audited_answer = await guardrails.audit_output(gen_result["answer"])
    gen_result["answer"] = audited_answer

    # 6. Cache Write
    await semantic_cache.set_cached_response(
        query=request.user_query,
        query_embedding=query_embed,
        response=audited_answer,
        sources=gen_result["sources"]
    )

    latency = (time.time() - start_time) * 1000
    gen_result["latency_ms"] = latency
    gen_result["cache_hit"] = False

    return gen_result


@app.post("/api/v1/stream")
async def query_stream(request: QueryRequest) -> StreamingResponse:
    # 1. Guardrails
    sanitized_query = await guardrails.sanitize_input(request.user_query)
    await guardrails.check_prompt_injection(sanitized_query)
    request.user_query = sanitized_query

    # 2. Retrieval
    query_response = await retriever.search(request)

    # 3. Streaming Generation
    generator = rag_generator.generate_stream(request.user_query, query_response.retrieved_chunks)

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
