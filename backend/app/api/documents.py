from datetime import datetime
from typing import Literal
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_admin
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.models.document_chunk import DocumentChunk
from app.services.permissions import document_access_clause, validate_document_permissions

import logging

from qdrant_client.models import PointStruct

from app.services.embeddings import embed_passages
from app.services.vector_store import COLLECTION_NAME, ensure_collection
from app.services.document_processing import (
    extract_document,
    build_document_chunks,
)

router = APIRouter(prefix="/documents", tags=["Documents"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_DIR = PROJECT_ROOT / "uploads"

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    file_size: int
    status: str
    uploaded_by: int
    created_at: datetime
    access_scope: str
    department_id: int | None


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=201,
)
def upload_document(
    file: UploadFile = File(...),
    access_scope: Literal["admin_only", "company", "department"] = Form("admin_only"),
    department_id: int | None = Form(default=None, ge=1),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    validate_document_permissions(db, access_scope, department_id)

    # Chỉ giữ tên file, loại bỏ phần đường dẫn từ client.
    original_name = (file.filename or "").replace("\\", "/")
    original_name = original_name.rsplit("/", 1)[-1].strip()

    if not original_name or len(original_name) > 255:
        raise HTTPException(
            status_code=400,
            detail="Tên file phải có từ 1 đến 255 ký tự",
        )

    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Chỉ nhận file PDF, DOCX hoặc TXT",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Tên do server tạo, tránh trùng hoặc ghi đè file khác.
    stored_name = f"{uuid4().hex}{extension}"
    destination = UPLOAD_DIR / stored_name
    size = 0

    try:
        with destination.open("xb") as output:
            while chunk := file.file.read(CHUNK_SIZE):
                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File vượt quá giới hạn 20 MB",
                    )

                output.write(chunk)

        if size == 0:
            raise HTTPException(
                status_code=400,
                detail="Không nhận file rỗng",
            )

        document = Document(
            original_name=original_name,
            stored_name=stored_name,
            file_size=size,
            status="uploaded",
            uploaded_by=admin.id,
            access_scope=access_scope,
            department_id=department_id,
        )

        db.add(document)
        db.flush()
        db.refresh(document)
        response = DocumentResponse.model_validate(document)
        db.commit()

    except Exception:
        db.rollback()
        destination.unlink(missing_ok=True)
        raise

    return response


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = (
        select(Document)
        .where(document_access_clause(user))
        .order_by(Document.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return db.scalars(statement).all()
@router.post("/{document_id}/process")
def process_document(
    document_id: int,
    force_ocr: bool = Query(default=False),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        document = db.scalar(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
        )

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy tài liệu",
            )

        if document.status != "uploaded":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Tài liệu không ở trạng thái uploaded. "
                    "Muốn thử cách xử lý khác, hãy tải lên bản mới."
                ),
            )

        file_path = UPLOAD_DIR / document.stored_name

        if not file_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy file gốc",
            )

        try:
            units, warnings = extract_document(
                file_path,
                force_ocr=force_ocr,
            )

            chunks = build_document_chunks(units)

        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            ) from error

        for chunk in chunks:
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    **chunk,
                )
            )

        document.status = "chunked"
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "document_id": document_id,
        "status": "chunked",
        "chunk_count": len(chunks),
        "character_count": sum(
            len(unit["text"]) for unit in units
        ),
        "ocr_pages": [
            unit["page_number"]
            for unit in units
            if unit["extracted_with"] == "ocr"
        ],
        "warnings": warnings,
    }
@router.get("/{document_id}/chunks")
def list_document_chunks(
    document_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    document = db.scalar(
        select(Document).where(
            Document.id == document_id, document_access_clause(user),
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy tài liệu",
        )

    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .offset(offset)
        .limit(limit)
    )

    chunks = db.scalars(statement).all()

    return [
        {
            "id": chunk.id,
            "document_id": chunk.document_id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "page_number": chunk.page_number,
            "source_location": chunk.source_location,
            "extracted_with": chunk.extracted_with,
        }
        for chunk in chunks
    ]

@router.post("/{document_id}/index")
def index_document(
    document_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        document = db.scalar(
            select(Document)
            .where(Document.id == document_id)
            .with_for_update()
        )

        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy tài liệu",
            )

        if document.status not in {"chunked", "indexed"}:
            raise HTTPException(
                status_code=409,
                detail="Cần chia đoạn tài liệu trước khi tạo vector",
            )

        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()

        if not chunks:
            raise HTTPException(
                status_code=409,
                detail="Tài liệu chưa có đoạn văn bản",
            )

        client = ensure_collection()

        # Xử lý từng lô nhỏ.
        for start in range(0, len(chunks), 16):
            batch = chunks[start:start + 16]

            vectors = embed_passages(
                [chunk.content for chunk in batch]
            )

            points = [
                PointStruct(
                    id=chunk.id,
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "chunk_index": chunk.chunk_index,
                    },
                )
                for chunk, vector in zip(batch, vectors)
            ]

            client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
                wait=True,
            )

        document.status = "indexed"
        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )

    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Document indexing failed: document_id=%s",
            document_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Chưa lập chỉ mục được. Kiểm tra log backend và Qdrant.",
        )

    return {
        "document_id": document_id,
        "status": "indexed",
        "indexed_chunks": len(chunks),
        "collection": COLLECTION_NAME,
    }

class DocumentPermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_scope: Literal["admin_only", "company", "department"]
    department_id: int | None = Field(default=None, ge=1)


@router.patch("/{document_id}/permissions", response_model=DocumentResponse)
def update_document_permissions(
    document_id: int,
    request: DocumentPermissionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    validate_document_permissions(db, request.access_scope, request.department_id)
    document = db.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if document is None:
        raise HTTPException(404, "Không tìm thấy tài liệu")
    document.access_scope = request.access_scope
    document.department_id = request.department_id
    db.flush()
    response = DocumentResponse.model_validate(document)
    db.commit()
    return response
