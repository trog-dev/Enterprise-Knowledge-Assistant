from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.department import Department  # Register foreign-key target


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "access_scope IN ('admin_only', 'company', 'department')",
            name="ck_documents_access_scope",
        ),
        CheckConstraint(
            "(access_scope = 'department' AND department_id IS NOT NULL) OR "
            "(access_scope <> 'department' AND department_id IS NULL)",
            name="ck_documents_scope_department",
        ),
    )

    access_scope: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="admin_only",
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True,
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    original_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="uploaded",
    )

    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )