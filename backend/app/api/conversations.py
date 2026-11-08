from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.session import get_db
from app.models.conversation import Conversation, ConversationTurn
from app.models.user import User
from app.services.permissions import accessible_document_ids, sources_are_visible

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime


class TurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    question: str
    answer: str
    sufficient: bool
    sources: list[dict]
    created_at: datetime


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(
            Conversation.created_at.desc(),
            Conversation.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    conversations = db.scalars(statement).all()
    if not conversations:
        return []
    allowed_ids = accessible_document_ids(db, user)
    rows = db.execute(
        select(ConversationTurn.conversation_id, ConversationTurn.sources)
        .where(ConversationTurn.conversation_id.in_([item.id for item in conversations]))
    ).all()
    hidden_titles = {
        conversation_id for conversation_id, sources in rows
        if not sources_are_visible(sources, allowed_ids)
    }
    return [
        ConversationResponse(
            id=item.id,
            title=("Hội thoại có nội dung bị giới hạn"
                   if item.id in hidden_titles else item.title),
            created_at=item.created_at,
        )
        for item in conversations
    ]


@router.get(
    "/{conversation_id}/turns",
    response_model=list[TurnResponse],
)
def list_conversation_turns(
    conversation_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy hội thoại",
        )

    statement = (
        select(ConversationTurn)
        .where(
            ConversationTurn.conversation_id == conversation_id
        )
        .order_by(ConversationTurn.id)
        .offset(offset)
        .limit(limit)
    )

    turns = db.scalars(statement).all()
    allowed_ids = accessible_document_ids(db, user)
    results = []
    for turn in turns:
        if not sources_are_visible(turn.sources, allowed_ids):
            # Hide the whole pair: filtering sources alone would still leak the answer.
            results.append(TurnResponse(
                id=turn.id,
                conversation_id=turn.conversation_id,
                question="[Nội dung đã bị giới hạn quyền truy cập]",
                answer="Bạn không còn quyền xem một hoặc nhiều nguồn của lượt này.",
                sufficient=False,
                sources=[],
                created_at=turn.created_at,
            ))
        else:
            results.append(TurnResponse.model_validate(turn))
    return results