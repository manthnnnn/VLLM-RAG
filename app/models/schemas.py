from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class DocumentMetadata(BaseModel):
    source_file: str
    department: str = Field(default="general")
    classification_level: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    author: str = Field(default="Unknown")
    custom_metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestionRequest(BaseModel):
    file_paths: Optional[List[str]] = None
    raw_texts: Optional[List[str]] = None
    metadata: DocumentMetadata

class IngestionResponse(BaseModel):
    total_documents: int
    total_chunks: int
    points_upserted: int
    elapsed_time_ms: float

class RetrievalFilter(BaseModel):
    departments: Optional[List[str]] = None
    min_classification_level: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class QueryRequest(BaseModel):
    user_query: str
    user_role: str = Field(default="employee")
    user_department: str = Field(default="general")
    top_k: int = Field(default=5, ge=1, le=100)
    alpha: float = Field(default=0.5, ge=0.0, le=1.0)

class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    source_file: str
    page_number: Optional[int] = None
    payload: Dict[str, Any]

class QueryResponse(BaseModel):
    query: str
    retrieved_chunks: List[RetrievedChunk]
    execution_latency_ms: float

class CollectionStats(BaseModel):
    collection_name: str
    total_points: int
    status: str
