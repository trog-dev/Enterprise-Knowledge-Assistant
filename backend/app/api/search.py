import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from qdrant_client.models import FieldCondition, Filter, MatchAny
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.embeddings import embed_query
from app.services.permissions import document_access_clause
from app.services.vector_store import (
    COLLECTION_NAME,
    ensure_collection,
)

router = APIRouter(prefix="/search", tags=["Search"])
logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)


class SearchResult(BaseModel):
    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    score: float
    page_number: int | None = None
    source_location: str | None = None


def retrieve_chunks(
    question: str,
    top_k: int,
    db: Session,
    user: User,
) -> list[SearchResult]:
    document_ids = list(
        db.scalars(
            select(Document.id)
            .where(Document.status == "indexed", document_access_clause(user))
        ).all()
    )

    if not document_ids:
        return []

    try:
        vector = embed_query(question)
        client = ensure_collection()

        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchAny(any=document_ids),
                    )
                ]
            ),
            limit=top_k,
            with_payload=False,
            with_vectors=False,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception("Search failed")

        raise HTTPException(
            status_code=503,
            detail=(
                "Chưa tìm kiếm được. "
                "Kiểm tra log backend và Qdrant."
            ),
        ) from error

    if not response.points:
        return []

    chunk_ids = [int(point.id) for point in response.points]

    rows = db.execute(
        select(DocumentChunk, Document)
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .where(
            DocumentChunk.id.in_(chunk_ids),
            Document.status == "indexed",
            document_access_clause(user),
        )
    ).all()

    by_id = {
        chunk.id: (chunk, document)
        for chunk, document in rows
    }

    results = []

    for point in response.points:
        row = by_id.get(int(point.id))

        if row is None:
            continue

        chunk, document = row

        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.original_name,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=point.score,
                page_number=chunk.page_number,
                source_location=chunk.source_location,
            )
        )

    return results


@router.post("", response_model=list[SearchResult])
def search_documents(
    request: SearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return retrieve_chunks(
        question=request.question,
        top_k=request.top_k,
        db=db,
        user=user,
    )