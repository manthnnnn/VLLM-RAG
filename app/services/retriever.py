import time
import asyncio
from typing import List, Optional
from loguru import logger
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from app.models.schemas import QueryRequest, QueryResponse, RetrievedChunk
from app.services.embeddings import embedding_engine
from app.config import settings


class HybridRetriever:
    def __init__(self, collection_name: str = "enterprise_knowledge"):
        self.qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        self.collection_name = collection_name

    def _build_rbac_filter(self, request: QueryRequest) -> Optional[models.Filter]:
        """
        Construct Qdrant payload filters enforcing RBAC.
        Returns None if no meaningful filter should be applied (e.g. guest/general role).
        Admin role bypasses filtering entirely.
        """
        role = request.user_role.lower()
        department = request.user_department.lower()
        clearance = self._role_to_clearance(role)

        # Admin sees everything
        if role == "admin":
            return None

        conditions = []

        # Only apply department filter if a real department is specified
        if department and department not in ("general", "all", ""):
            conditions.append(
                models.FieldCondition(
                    key="department",
                    match=models.MatchAny(any=[department, "general"])
                )
            )

        # Apply clearance level filter
        conditions.append(
            models.FieldCondition(
                key="classification_level",
                range=models.Range(lte=clearance)
            )
        )

        if not conditions:
            return None

        return models.Filter(must=conditions)

    def _role_to_clearance(self, role: str) -> int:
        role_map = {
            "admin": 5,
            "manager": 3,
            "employee": 2,
            "guest": 1,
        }
        return role_map.get(role.lower(), 1)

    async def search(self, request: QueryRequest) -> QueryResponse:
        start_time = time.time()

        # 1. Generate query embeddings
        dense_embeds, sparse_embeds = await embedding_engine.generate_embeddings_batch(
            [request.user_query], batch_size=1
        )

        query_dense = dense_embeds[0]
        query_sparse_dict = sparse_embeds[0]
        query_sparse = models.SparseVector(
            indices=list(query_sparse_dict.keys()),
            values=list(query_sparse_dict.values())
        )

        # 2. Build optional RBAC Filters
        rbac_filter = self._build_rbac_filter(request)

        # 3. Execute Hybrid Search using Prefetch + RRF Fusion (Qdrant v1.7+)
        prefetch_dense = models.Prefetch(
            query=query_dense,
            using="dense",
            limit=request.top_k * 2,
            filter=rbac_filter
        )

        prefetch_sparse = models.Prefetch(
            query=query_sparse,
            using="sparse",
            limit=request.top_k * 2,
            filter=rbac_filter
        )

        try:
            search_result = await self.qdrant.query_points(
                collection_name=self.collection_name,
                prefetch=[prefetch_dense, prefetch_sparse],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=request.top_k,
                with_payload=True,
            )
            points = search_result.points
        except Exception as e:
            logger.warning(f"Qdrant search failed (falling back to empty): {e}")
            latency_ms = (time.time() - start_time) * 1000
            return QueryResponse(
                query=request.user_query,
                retrieved_chunks=[],
                execution_latency_ms=latency_ms
            )

        # 4. Format Output
        retrieved_chunks = []
        for point in points:
            payload = point.payload or {}
            retrieved_chunks.append(
                RetrievedChunk(
                    chunk_id=str(point.id),
                    text=payload.get("text", ""),
                    score=point.score,
                    source_file=payload.get("source_file", "unknown"),
                    page_number=payload.get("page_number"),
                    payload={k: v for k, v in payload.items() if k != "text"}
                )
            )

        latency_ms = (time.time() - start_time) * 1000

        return QueryResponse(
            query=request.user_query,
            retrieved_chunks=retrieved_chunks,
            execution_latency_ms=latency_ms
        )


retriever = HybridRetriever()
