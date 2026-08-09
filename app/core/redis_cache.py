import json
import hashlib
import math
from typing import Dict, Any, Optional, List
import redis.asyncio as redis
from loguru import logger
from app.config import settings


def _sha256_key(text: str) -> str:
    """Stable, cross-restart-safe hash for cache keys."""
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class SemanticCache:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        # In-memory index of (key -> embedding) for semantic similarity lookup
        # This provides real semantic caching without requiring RediSearch/VSS module
        self._embedding_index: Dict[str, List[float]] = {}

    async def connect(self):
        try:
            self.redis_client = redis.from_url(settings.redis_url, decode_responses=True)
            await self.redis_client.ping()
            # Rebuild in-memory embedding index from Redis keys
            await self._rebuild_embedding_index()
            logger.info("Connected to Redis cache and rebuilt semantic index.")
        except Exception as e:
            logger.warning(f"Redis unavailable (cache disabled): {e}")
            self.redis_client = None

    async def disconnect(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Disconnected from Redis cache.")

    async def _rebuild_embedding_index(self) -> None:
        """Reload embedding vectors from Redis into memory on startup."""
        if not self.redis_client:
            return
        try:
            keys = await self.redis_client.keys("cache:embed:*")
            for key in keys:
                embed_str = await self.redis_client.get(key)
                if embed_str:
                    cache_key = key.replace("cache:embed:", "")
                    self._embedding_index[cache_key] = json.loads(embed_str)
            logger.info(f"Rebuilt semantic index with {len(self._embedding_index)} entries.")
        except Exception as e:
            logger.warning(f"Failed to rebuild embedding index: {e}")

    async def get_cached_response(
        self,
        query: str,
        query_embedding: List[float],
        threshold: float = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached response using semantic similarity.
        First checks exact hash match (instant), then does cosine similarity
        across all stored embeddings (semantic match).
        """
        if not self.redis_client:
            return None

        if threshold is None:
            threshold = settings.semantic_cache_threshold

        try:
            # --- Pass 1: Exact Match (O(1)) ---
            exact_key = f"cache:data:{_sha256_key(query)}"
            cached_str = await self.redis_client.get(exact_key)
            if cached_str:
                logger.info(f"Cache HIT (Exact) for: '{query[:60]}'")
                return json.loads(cached_str)

            # --- Pass 2: Semantic Similarity Search ---
            best_key: Optional[str] = None
            best_score: float = 0.0

            for cached_hash, cached_embed in self._embedding_index.items():
                score = _cosine_similarity(query_embedding, cached_embed)
                if score > best_score:
                    best_score = score
                    best_key = cached_hash

            if best_key and best_score >= threshold:
                data_key = f"cache:data:{best_key}"
                cached_str = await self.redis_client.get(data_key)
                if cached_str:
                    logger.info(
                        f"Cache HIT (Semantic, score={best_score:.4f}) for: '{query[:60]}'"
                    )
                    return json.loads(cached_str)

            logger.debug(f"Cache MISS (best_score={best_score:.4f}, threshold={threshold})")
            return None

        except Exception as e:
            logger.error(f"Redis cache read error: {e}")
            return None

    async def set_cached_response(
        self,
        query: str,
        query_embedding: List[float],
        response: str,
        sources: List[Dict[str, Any]]
    ) -> None:
        """Store response + embedding in Redis and update in-memory index."""
        if not self.redis_client:
            return

        try:
            cache_hash = _sha256_key(query)

            # Store the response data
            data_key = f"cache:data:{cache_hash}"
            data = {
                "query": query,
                "answer": response,
                "sources": sources,
                "cache_hit": True,
            }
            await self.redis_client.setex(
                name=data_key,
                time=settings.redis_cache_ttl,
                value=json.dumps(data)
            )

            # Store the embedding separately for semantic index
            embed_key = f"cache:embed:{cache_hash}"
            await self.redis_client.setex(
                name=embed_key,
                time=settings.redis_cache_ttl,
                value=json.dumps(query_embedding)
            )

            # Update in-memory index
            self._embedding_index[cache_hash] = query_embedding

            logger.info(f"Cached response + embedding for: '{query[:60]}'")

        except Exception as e:
            logger.error(f"Redis cache write error: {e}")


semantic_cache = SemanticCache()
