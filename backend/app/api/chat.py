from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.search import SearchResult, retrieve_chunks
from app.db.session import get_db
from app.models.user import User
from app.services.gemini import GeminiError, generate_answer
from app.models.conversation import Conversation, ConversationTurn
from app.services.permissions import check_answer_access

router = APIRouter(prefix="/chat", tags=["Chat"])

NO_INFORMATION = (
    "Chưa đủ thông tin trong các tài liệu tìm được "
    "để trả lời câu hỏi này."
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)
    conversation_id: int | None = Field(default=None, ge=1)


class Citation(BaseModel):
    source_id: str
    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    page_number: int | None = None
    source_location: str | None = None


class ChatResponse(BaseModel):
    question: str
    answer: str
    sufficient: bool
    sources: list[Citation]
    conversation_id: int | None = None
    turn_id: int | None = None
def save_chat_response(
    db: Session,
    conversation: Conversation,
    response: ChatResponse,
) -> ChatResponse:
    try:
        turn = ConversationTurn(
            conversation_id=conversation.id,
            question=response.question,
            answer=response.answer,
            sufficient=response.sufficient,
            sources=[
                source.model_dump(mode="json")
                for source in response.sources
            ],
        )

        db.add(turn)
        db.flush()

        response.conversation_id = conversation.id
        response.turn_id = turn.id

        db.commit()

    except Exception:
        db.rollback()
        raise

    return response

@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Tạo hội thoại mới hoặc kiểm tra hội thoại đã có.
    if request.conversation_id is None:
        conversation = Conversation(
            user_id=user.id,
            title=request.question[:120],
        )

        db.add(conversation)
        db.flush()

    else:
        conversation = db.get(
            Conversation,
            request.conversation_id,
        )

        if (
            conversation is None
            or conversation.user_id != user.id
        ):
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy hội thoại",
            )

    # Tìm các đoạn tài liệu liên quan.
    hits: list[SearchResult] = retrieve_chunks(
        question=request.question,
        top_k=request.top_k,
        db=db,
        user=user,
    )

    if not hits:
        return save_chat_response(
            db=db,
            conversation=conversation,
            response=ChatResponse(
                question=request.question,
                answer=NO_INFORMATION,
                sufficient=False,
                sources=[],
            ),
        )

    source_map = {
        f"C{hit.chunk_id}": hit
        for hit in hits
    }

    context = [
        {
            "source_id": source_id,
            "document_name": hit.document_name,
            "chunk_index": hit.chunk_index,
            "content": hit.content,
            "page_number": hit.page_number,
            "source_location": hit.source_location,
        }
        for source_id, hit in source_map.items()
    ]

    # Sinh câu trả lời từ các đoạn nguồn.
    try:
        generated = generate_answer(
            question=request.question,
            sources=context,
        )
    except GeminiError as error:
        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    check_answer_access(db, user, {hit.document_id for hit in hits})

    if not generated.sufficient:
        return save_chat_response(
            db=db,
            conversation=conversation,
            response=ChatResponse(
                question=request.question,
                answer=NO_INFORMATION,
                sufficient=False,
                sources=[],
            ),
        )

    citations = []

    for source_id in dict.fromkeys(generated.source_ids):
        hit = source_map[source_id]

        citations.append(
            Citation(
                source_id=source_id,
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_name=hit.document_name,
                chunk_index=hit.chunk_index,
                content=hit.content,
                page_number=hit.page_number,
                source_location=hit.source_location,
            )
        )

    # Lưu câu trả lời và nguồn trước khi trả kết quả.
    return save_chat_response(
        db=db,
        conversation=conversation,
        response=ChatResponse(
            question=request.question,
            answer=generated.answer.strip(),
            sufficient=True,
            sources=citations,
        ),
    )