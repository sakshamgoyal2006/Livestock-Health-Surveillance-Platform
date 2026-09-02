from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import User


class IdentityAdapter(Protocol):
    async def authenticate(
        self, *, session: AsyncSession, email: str, role: str, password: str
    ) -> User | None: ...


class DevelopmentIdentityAdapter:
    """Local-only adapter. It never creates users or accepts arbitrary roles."""

    async def authenticate(
        self, *, session: AsyncSession, email: str, role: str, password: str
    ) -> User | None:
        if password != "dev-only":
            return None
        user = await session.scalar(
            select(User).where(
                User.email == email.lower(),
                User.role == role,
                User.active.is_(True),
                User.synthetic.is_(True),
            )
        )
        return user


class ProductionIdentityAdapter:
    """OIDC boundary; deliberately unavailable until a provider is configured."""

    async def authenticate(
        self, *, session: AsyncSession, email: str, role: str, password: str
    ) -> User | None:
        del session, email, role, password
        raise RuntimeError("Production identity provider is not configured")
