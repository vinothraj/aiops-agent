import uuid
import logging
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
import google.generativeai as genai
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.models import KnowledgeDocument, IncidentHistory, Runbook

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        self.collection_name = "knowledge_base"
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(path=settings.QDRANT_PATH)
            self._init_collection()
        return self._client

    def _init_collection(self):
        # The text-embedding-004 model produces 768-dimensional embeddings
        vector_size = 768
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=qdrant_models.Distance.COSINE
                )
            )

    def generate_embedding(self, text: str, task_type: str = "retrieval_document") -> List[float]:
        """Generate text embedding using Google Gemini."""
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured.")
        
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        result = genai.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            content=text,
            task_type=task_type
        )
        return result['embedding']

    def ingest_document(self, db: Session, title: str, content: str, doc_type: str, source_id: Optional[str] = None) -> KnowledgeDocument:
        """Embed a document and store it in both Qdrant and SQLite."""
        # 1. Save to SQLite
        point_id = str(uuid.uuid4())
        doc = KnowledgeDocument(
            title=title,
            content=content,
            doc_type=doc_type,
            source_id=source_id,
            qdrant_point_id=point_id
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        # 2. Generate Embedding
        text_to_embed = f"Title: {title}\nType: {doc_type}\nContent: {content}"
        vector = self.generate_embedding(text_to_embed, task_type="retrieval_document")

        # 3. Save to Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "title": title,
                        "doc_type": doc_type,
                        "source_id": source_id,
                        "sqlite_id": doc.id,
                        "content": content
                    }
                )
            ]
        )
        logger.info(f"Ingested document into RAG: {title} ({doc_type})")
        return doc

    def search_similar_incidents(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search Qdrant for similar incidents based on the error log query."""
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set. RAG search skipped.")
            return [] 
            
        try:
            query_vector = self.generate_embedding(query, task_type="retrieval_query")

            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit
            )
            
            results = []
            for hit in search_result:
                # Filter out low relevance results if needed. Cosine distance 1 is max, so score is 1 - dist.
                # Usually higher score is better for cosine distance in qdrant
                results.append({
                    "score": hit.score,
                    "title": hit.payload.get("title"),
                    "doc_type": hit.payload.get("doc_type"),
                    "content": hit.payload.get("content"),
                    "source_id": hit.payload.get("source_id")
                })
                
            return results
        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return []

rag_service = RAGService()
