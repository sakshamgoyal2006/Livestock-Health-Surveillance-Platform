from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import APIModel

RoleValue = Literal["FARMER", "FIELD_WORKER", "VETERINARIAN", "DISTRICT_OFFICER", "ADMIN"]


class DevLoginRequest(APIModel):
    email: EmailStr
    role: RoleValue
    password: str = Field(min_length=6, max_length=128)


class UserOut(APIModel):
    id: UUID
    email: EmailStr
    display_name: str
    role: RoleValue


class TokenResponse(APIModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut
