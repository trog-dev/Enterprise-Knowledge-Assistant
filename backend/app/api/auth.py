import secrets
from typing import Literal

import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.models.department import Department

router = APIRouter(prefix="/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Dùng khi email không tồn tại để vẫn thực hiện kiểm tra mật khẩu.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    department_id: int | None = None


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Thông tin đăng nhập hoặc token không hợp lệ",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat"]},
        )

        subject = payload["sub"]

        if not isinstance(subject, str):
            raise ValueError("Invalid subject")

        user_id = int(subject)

        if user_id <= 0:
            raise ValueError("Invalid user ID")

    except (InvalidTokenError, ValueError, TypeError):
        raise unauthorized()

    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise unauthorized()

    return user


@router.post("/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form.username.strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    stored_hash = (
        user.password_hash if user is not None
        else DUMMY_PASSWORD_HASH
    )

    password_matches = verify_password(
        form.password,
        stored_hash,
    )

    if user is None or not password_matches:
        raise unauthorized()

    if not user.is_active:
        raise unauthorized()

    return TokenResponse(
        access_token=create_access_token(user.id)
    )


@router.get("/me", response_model=UserResponse)
def read_current_user(
    user: User = Depends(get_current_user),
):
    return user

def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản trị viên được thực hiện thao tác này",
        )

    return user

class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9_]+$")
    name: str = Field(min_length=1, max_length=150)


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "employee"] = "employee"
    department_id: int | None = Field(default=None, ge=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        import re
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Email không hợp lệ")
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Họ tên không được rỗng")
        return value


class UserAccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    department_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @field_validator("is_active", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("is_active phải là true hoặc false")
        return value


def validate_department(db: Session, department_id: int | None):
    if department_id is not None and db.get(Department, department_id) is None:
        raise HTTPException(422, "Phòng ban không tồn tại")


@router.get("/departments", response_model=list[DepartmentResponse])
def list_departments(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return db.scalars(
        select(Department).order_by(Department.id).offset(offset).limit(limit)
    ).all()


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
def create_department(
    request: DepartmentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    department = Department(code=request.code, name=request.name)
    try:
        db.add(department)
        db.flush()
        response = DepartmentResponse.model_validate(department)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Mã phòng ban đã tồn tại") from None
    return response


@router.get("/users", response_model=list[UserResponse])
def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    return db.scalars(
        select(User).order_by(User.id).offset(offset).limit(limit)
    ).all()


@router.post("/users", response_model=UserResponse, status_code=201)
def create_user(
    request: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    validate_department(db, request.department_id)
    if db.scalar(select(User.id).where(User.email == request.email)) is not None:
        raise HTTPException(409, "Email đã tồn tại")
    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
        role=request.role,
        department_id=request.department_id,
        is_active=True,
    )
    try:
        db.add(user)
        db.flush()
        response = UserResponse.model_validate(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dữ liệu tài khoản xung đột; tải lại danh sách") from None
    return response


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user_access(
    user_id: int,
    request: UserAccessUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    fields = request.model_fields_set
    if not fields:
        raise HTTPException(422, "Cần gửi trường muốn thay đổi")
    if "is_active" in fields and user.role == "admin":
        raise HTTPException(409, "API này chỉ khóa/mở tài khoản nhân viên")
    if "department_id" in fields:
        validate_department(db, request.department_id)
        user.department_id = request.department_id
    if "is_active" in fields:
        user.is_active = request.is_active
    db.flush()
    response = UserResponse.model_validate(user)
    db.commit()
    return response
