from fastapi import HTTPException
from sqlalchemy import and_, false, or_, select, true
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.document import Document
from app.models.user import User


def document_access_clause(user: User):
    """A single policy for listing, chunks, retrieval and saved sources."""
    if not user.is_active:
        return false()
    if user.role == "admin":
        return true()
    if user.role != "employee":
        return false()
    company = Document.access_scope == "company"
    if user.department_id is None:
        return company
    return or_(
        company,
        and_(
            Document.access_scope == "department",
            Document.department_id == user.department_id,
        ),
    )


def accessible_document_ids(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(Document.id).where(document_access_clause(user))))


def sources_are_visible(sources, allowed_ids: set[int]) -> bool:
    # Old or malformed source data never grants access.
    if not isinstance(sources, list):
        return False
    return all(
        isinstance(source, dict)
        and type(source.get("document_id")) is int
        and source["document_id"] in allowed_ids
        for source in sources
    )


def validate_document_permissions(
    db: Session, access_scope: str, department_id: int | None,
) -> None:
    if access_scope not in {"admin_only", "company", "department"}:
        raise HTTPException(422, "Phạm vi truy cập không hợp lệ")
    if access_scope == "department":
        if department_id is None or db.get(Department, department_id) is None:
            raise HTTPException(422, "Cần chọn phòng ban tồn tại")
    elif department_id is not None:
        raise HTTPException(422, "Chỉ tài liệu riêng phòng ban mới có department_id")


def check_answer_access(db: Session, user: User, document_ids: set[int]) -> None:
    """Recheck after generation so a changed ACL cannot return an old answer."""
    db.refresh(user)
    if not user.is_active:
        raise HTTPException(401, "Tài khoản đã bị khóa")
    visible = set(db.scalars(
        select(Document.id).where(
            Document.id.in_(document_ids), document_access_clause(user),
        )
    )) if document_ids else set()
    if visible != document_ids:
        raise HTTPException(
            409, "Quyền tài liệu đã thay đổi trong lúc xử lý. Hãy gửi lại câu hỏi.",
        )
