import asyncio
import time
from typing import List, Optional
from loguru import logger
import PyPDF2
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from app.models.schemas import IngestionRequest, IngestionResponse, DocumentMetadata
from app.services.chunking import RecursiveCharacterChunker
from app.services.embeddings import embedding_engine
from app.config import settings

class DocumentIngestionService:
    def __init__(self, collection_name: str = "enterprise_knowledge"):
        self.qdrant = AsyncQdrantClient(url=settings.qdrant_url)
        self.collection_name = collection_name
        self.chunker = RecursiveCharacterChunker(chunk_size=512, chunk_overlap=64)
        
    async def initialize_collection(self) -> None:
        """Create Qdrant collection with Dense and Sparse vector configurations if not exists."""
        try:
            exists = await self.qdrant.collection_exists(self.collection_name)
            if not exists:
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                await self.qdrant.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "dense": models.VectorParams(
                            size=384,  # size for BAAI/bge-small-en-v1.5
                            distance=models.Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        "sparse": models.SparseVectorParams(
                            modifier=models.Modifier.IDF
                        )
                    }
                )
                # Create payload indices for fast RBAC filtering
                await self.qdrant.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="department",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
                await self.qdrant.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="classification_level",
                    field_schema=models.PayloadSchemaType.INTEGER,
                )
            else:
                logger.info(f"Collection {self.collection_name} already exists.")
        except Exception as e:
            logger.warning(f"Qdrant unavailable at startup (demo mode will handle queries): {e}")

    def _extract_text_from_pdf(self, file_path: str) -> str:
        text = ""
        try:
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.error(f"Error reading PDF {file_path}: {e}")
        return text

    def _read_text_file(self, file_path: str) -> str:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return ""

    async def process_ingestion(self, request: IngestionRequest) -> IngestionResponse:
        start_time = time.time()
        await self.initialize_collection()
        
        all_chunks = []
        document_count = 0
        
        metadata_dict = request.metadata.model_dump()
        # Ensure datetimes are serialized to strings
        if "created_at" in metadata_dict and metadata_dict["created_at"]:
            metadata_dict["created_at"] = metadata_dict["created_at"].isoformat()

        if request.file_paths:
            for file_path in request.file_paths:
                if file_path.lower().endswith(".pdf"):
                    text = self._extract_text_from_pdf(file_path)
                else:
                    text = self._read_text_file(file_path)
                
                if text:
                    document_count += 1
                    doc_chunks = await self.chunker.chunk_document(
                        text=text, 
                        document_id=file_path, 
                        metadata=metadata_dict
                    )
                    all_chunks.extend(doc_chunks)

        if request.raw_texts:
            for idx, text in enumerate(request.raw_texts):
                if text:
                    document_count += 1
                    doc_chunks = await self.chunker.chunk_document(
                        text=text, 
                        document_id=f"raw_text_{idx}", 
                        metadata=metadata_dict
                    )
                    all_chunks.extend(doc_chunks)

        if not all_chunks:
            return IngestionResponse(
                total_documents=document_count,
                total_chunks=0,
                points_upserted=0,
                elapsed_time_ms=(time.time() - start_time) * 1000
            )

        # Generate Embeddings
        texts = [chunk["text"] for chunk in all_chunks]
        dense_embeddings, sparse_embeddings = await embedding_engine.generate_embeddings_batch(texts)

        # Prepare Qdrant Points
        points = []
        for i, chunk in enumerate(all_chunks):
            sparse_vec = sparse_embeddings[i]
            points.append(
                models.PointStruct(
                    id=chunk["chunk_id"],
                    vector={
                        "dense": dense_embeddings[i],
                        "sparse": models.SparseVector(
                            indices=list(sparse_vec.keys()),
                            values=list(sparse_vec.values())
                        )
                    },
                    payload=chunk["metadata"]
                )
            )

        # Upsert in chunks of 100
        upserted_count = 0
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await self.qdrant.upsert(
                collection_name=self.collection_name,
                points=batch
            )
            upserted_count += len(batch)
            logger.info(f"Upserted {upserted_count}/{len(points)} points")

        return IngestionResponse(
            total_documents=document_count,
            total_chunks=len(all_chunks),
            points_upserted=upserted_count,
            elapsed_time_ms=(time.time() - start_time) * 1000
        )
