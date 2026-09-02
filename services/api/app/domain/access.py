from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Farm, OwnershipAssignment, User


class Actor(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def role(self) -> str: ...


@dataclass(frozen=True)
class ActorIdentity:
    id: UUID
    role: str


async def can_manage_farm(session: AsyncSession, user: Actor, farm_id: UUID) -> bool:
    farm = await session.get(Farm, farm_id)
    if farm is None:
        return False
    if user.role == "ADMIN" or farm.owner_user_id == user.id:
        return True
    if user.role == "FIELD_WORKER":
        return bool(
            await session.scalar(
                select(
                    exists().where(
                        OwnershipAssignment.farm_id == farm_id,
                        OwnershipAssignment.user_id == user.id,
                        OwnershipAssignment.active.is_(True),
                    )
                )
            )
        )
    return False


async def can_read_report(session: AsyncSession, user: User, reporter_user_id: UUID) -> bool:
    if user.role in {"VETERINARIAN", "DISTRICT_OFFICER", "ADMIN"}:
        return True
    return user.id == reporter_user_id
