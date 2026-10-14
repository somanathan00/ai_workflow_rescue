
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: UserRole
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: UUID
    exp: int
