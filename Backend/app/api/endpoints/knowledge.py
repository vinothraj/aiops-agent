from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database.session import get_db
from app.services.rag.rag_service import rag_service

router = APIRouter()

class IngestRequest(BaseModel):
    title: str
    content: str
    doc_type: str = "RUNBOOK" # 'RUNBOOK', 'INCIDENT', 'GUIDE'
    source_id: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    limit: int = 5

@router.post("/ingest")
def ingest_knowledge(request: IngestRequest, db: Session = Depends(get_db)):
    """Ingest a new document into the RAG Knowledge Base."""
    try:
        doc = rag_service.ingest_document(
            db=db,
            title=request.title,
            content=request.content,
            doc_type=request.doc_type,
            source_id=request.source_id
        )
        return {"status": "success", "id": doc.id, "qdrant_point_id": doc.qdrant_point_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

@router.post("/search")
def search_knowledge(request: SearchRequest):
    """Manually test searching the RAG Knowledge Base."""
    try:
        results = rag_service.search_similar_incidents(request.query, request.limit)
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
