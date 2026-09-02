from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.models import FarmerProfile, FieldWorkerProfile, User, VeterinarianProfile

SYNTHETIC_USERS = [
    (
        UUID("11111111-1111-4111-8111-111111111111"),
        "farmer@example.com",
        "Synthetic Farmer",
        "FARMER",
    ),
    (
        UUID("22222222-2222-4222-8222-222222222222"),
        "field@example.com",
        "Synthetic Field Worker",
        "FIELD_WORKER",
    ),
    (
        UUID("33333333-3333-4333-8333-333333333333"),
        "vet@example.com",
        "Synthetic Veterinarian",
        "VETERINARIAN",
    ),
    (
        UUID("44444444-4444-4444-8444-444444444444"),
        "officer@example.com",
        "Synthetic District Officer",
        "DISTRICT_OFFICER",
    ),
    (
        UUID("55555555-5555-4555-8555-555555555555"),
        "admin@example.com",
        "Synthetic Administrator",
        "ADMIN",
    ),
]


async def seed() -> None:
    async with SessionLocal() as session:
        for user_id, email, display_name, role in SYNTHETIC_USERS:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    id=user_id,
                    email=email,
                    display_name=display_name,
                    role=role,
                    active=True,
                    synthetic=True,
                )
                session.add(user)
                await session.flush()
            if role == "FARMER" and not await session.scalar(
                select(FarmerProfile).where(FarmerProfile.user_id == user.id)
            ):
                session.add(FarmerProfile(user_id=user.id, preferred_language="mr"))
            if role == "FIELD_WORKER" and not await session.scalar(
                select(FieldWorkerProfile).where(FieldWorkerProfile.user_id == user.id)
            ):
                session.add(
                    FieldWorkerProfile(user_id=user.id, service_area="Synthetic Pune demo area")
                )
            if role == "VETERINARIAN" and not await session.scalar(
                select(VeterinarianProfile).where(VeterinarianProfile.user_id == user.id)
            ):
                session.add(
                    VeterinarianProfile(
                        user_id=user.id,
                        registration_reference="SYNTHETIC-NOT-A-REAL-REGISTRATION",
                        synthetic=True,
                    )
                )
        await session.commit()
    print("Loaded 5 explicitly synthetic development identities (idempotent).")


if __name__ == "__main__":
    asyncio.run(seed())
