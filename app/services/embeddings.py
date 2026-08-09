import os
import random
from typing import List, Dict, Any, Tuple
from loguru import logger
import asyncio

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

class MockEmbeddingEngine:
    """Lightweight mock used when DEMO_MODE=true and full models aren't needed."""
    VECTOR_DIM = 384

    async def generate_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> Tuple[List[List[float]], List[Dict[int, float]]]:
        logger.info(f"[Demo] Mock embedding for {len(texts)} texts")
        dense = [[random.uniform(-0.1, 0.1) for _ in range(self.VECTOR_DIM)] for _ in texts]
        sparse = [{random.randint(0, 30000): random.uniform(0.1, 1.0) for _ in range(20)} for _ in texts]
        return dense, sparse

class DualEmbeddingEngine:
    def __init__(self, dense_model_name: str = "BAAI/bge-small-en-v1.5", sparse_model_name: str = "prithivida/Splade_PP_en_v1"):
        if DEMO_MODE:
            logger.info("Demo mode: using mock embedding engine (no model download needed)")
            self.dense_model = None
            self.sparse_model = None
            self._mock = MockEmbeddingEngine()
        else:
            try:
                from fastembed import TextEmbedding, SparseTextEmbedding
                logger.info(f"Initializing Dense Embedding model: {dense_model_name}")
                self.dense_model = TextEmbedding(model_name=dense_model_name)
                logger.info(f"Initializing Sparse Embedding model: {sparse_model_name}")
                self.sparse_model = SparseTextEmbedding(model_name=sparse_model_name)
                self._mock = None
            except Exception as e:
                logger.warning(f"Failed to load embedding models, falling back to mock: {e}")
                self.dense_model = None
                self.sparse_model = None
                self._mock = MockEmbeddingEngine()

    async def generate_embeddings_batch(self, texts: List[str], batch_size: int = 32) -> Tuple[List[List[float]], List[Dict[int, float]]]:
        """Generate dense and sparse embeddings concurrently."""
        if self._mock is not None:
            return await self._mock.generate_embeddings_batch(texts, batch_size)

        loop = asyncio.get_running_loop()
        
        def _compute_dense() -> List[List[float]]:
            return [vec.tolist() for vec in self.dense_model.embed(texts, batch_size=batch_size)]

        def _compute_sparse() -> List[Dict[int, float]]:
            sparse_results = []
            for sparse_vec in self.sparse_model.embed(texts, batch_size=batch_size):
                sparse_dict = {int(idx): float(val) for idx, val in zip(sparse_vec.indices, sparse_vec.values)}
                sparse_results.append(sparse_dict)
            return sparse_results

        logger.debug(f"Generating embeddings for {len(texts)} chunks...")
        dense_task = loop.run_in_executor(None, _compute_dense)
        sparse_task = loop.run_in_executor(None, _compute_sparse)

        dense_embeddings, sparse_embeddings = await asyncio.gather(dense_task, sparse_task)
        
        return dense_embeddings, sparse_embeddings

embedding_engine = DualEmbeddingEngine()
