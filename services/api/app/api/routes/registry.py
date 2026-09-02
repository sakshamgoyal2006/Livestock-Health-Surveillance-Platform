from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from geoalchemy2.elements import WKTElement
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep, require_roles
from app.core.audit import append_audit
from app.domain.access import can_manage_farm
from app.domain.models import Animal, Farm, Herd, OwnershipAssignment, User
from app.schemas.registry import AnimalCreate, AnimalOut, FarmCreate, FarmOut, HerdCreate, HerdOut

router = APIRouter(prefix="/api/v1", tags=["registry"])
RegistryActor = Annotated[User, Depends(require_roles("FARMER", "FIELD_WORKER", "ADMIN"))]


def point(body: FarmCreate) -> WKTElement | None:
    if body.latitude is None or body.longitude is None:
        return None
    return WKTElement(f"POINT({body.longitude} {body.latitude})", srid=4326)


@router.post("/farms", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
async def create_farm(
    body: FarmCreate, request: Request, session: SessionDep, actor: RegistryActor
) -> FarmOut:
    farm = Farm(
        id=body.id,
        owner_user_id=actor.id,
        name=body.name,
        village_name=body.village_name,
        location=point(body),
        latitude=body.latitude,
        longitude=body.longitude,
        location_precision=body.location_precision,
        synthetic=False,
    )
    session.add(farm)
    try:
        await session.flush()
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="FARM_CREATED",
            resource_type="farm",
            resource_id=farm.id,
            request_id=request.state.request_id,
            details={"location_precision": body.location_precision},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "FARM_CONFLICT", "message": "Farm ID already exists"},
        ) from exc
    await session.refresh(farm)
    return FarmOut.model_validate(farm)


@router.get("/farms", response_model=list[FarmOut])
async def list_farms(session: SessionDep, actor: RegistryActor) -> list[FarmOut]:
    if actor.role == "ADMIN":
        query = select(Farm)
    elif actor.role == "FIELD_WORKER":
        assigned = select(OwnershipAssignment.farm_id).where(
            OwnershipAssignment.user_id == actor.id,
            OwnershipAssignment.active.is_(True),
        )
        query = select(Farm).where(or_(Farm.owner_user_id == actor.id, Farm.id.in_(assigned)))
    else:
        query = select(Farm).where(Farm.owner_user_id == actor.id)
    farms = (await session.scalars(query.order_by(Farm.created_at.desc()))).all()
    return [FarmOut.model_validate(farm) for farm in farms]


@router.post("/herds", response_model=HerdOut, status_code=status.HTTP_201_CREATED)
async def create_herd(
    body: HerdCreate, request: Request, session: SessionDep, actor: RegistryActor
) -> HerdOut:
    if not await can_manage_farm(session, actor, body.farm_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "FARM_NOT_FOUND", "message": "Farm is missing or inaccessible"},
        )
    herd = Herd(
        id=body.id,
        farm_id=body.farm_id,
        name=body.name,
        species=body.species,
        animal_count=body.animal_count,
        created_by_user_id=actor.id,
    )
    session.add(herd)
    try:
        await session.flush()
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="HERD_CREATED",
            resource_type="herd",
            resource_id=herd.id,
            request_id=request.state.request_id,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "HERD_CONFLICT", "message": "Herd could not be created"},
        ) from exc
    await session.refresh(herd)
    return HerdOut.model_validate(herd)


@router.get("/herds", response_model=list[HerdOut])
async def list_herds(session: SessionDep, actor: RegistryActor) -> list[HerdOut]:
    farm_ids = select(Farm.id).where(Farm.owner_user_id == actor.id)
    query = select(Herd).where(Herd.farm_id.in_(farm_ids))
    if actor.role == "ADMIN":
        query = select(Herd)
    herds = (await session.scalars(query.order_by(Herd.created_at.desc()))).all()
    return [HerdOut.model_validate(herd) for herd in herds]


@router.post("/animals", response_model=AnimalOut, status_code=status.HTTP_201_CREATED)
async def create_animal(
    body: AnimalCreate, request: Request, session: SessionDep, actor: RegistryActor
) -> AnimalOut:
    if not await can_manage_farm(session, actor, body.farm_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "FARM_NOT_FOUND", "message": "Farm is missing or inaccessible"},
        )
    if body.herd_id is not None:
        herd = await session.get(Herd, body.herd_id)
        if herd is None or herd.farm_id != body.farm_id or herd.species != body.species:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_HERD", "message": "Herd does not match farm and species"},
            )
    animal = Animal(
        id=body.id,
        farm_id=body.farm_id,
        herd_id=body.herd_id,
        tag_number=body.tag_number,
        species=body.species,
        sex=body.sex,
        age_band=body.age_band,
        created_by_user_id=actor.id,
    )
    session.add(animal)
    try:
        await session.flush()
        await append_audit(
            session,
            actor_user_id=actor.id,
            action="ANIMAL_CREATED",
            resource_type="animal",
            resource_id=animal.id,
            request_id=request.state.request_id,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "ANIMAL_CONFLICT", "message": "Animal ID or farm tag already exists"},
        ) from exc
    await session.refresh(animal)
    return AnimalOut.model_validate(animal)


@router.get("/animals", response_model=list[AnimalOut])
async def list_animals(session: SessionDep, actor: RegistryActor) -> list[AnimalOut]:
    farm_ids = select(Farm.id).where(Farm.owner_user_id == actor.id)
    query = select(Animal).where(Animal.farm_id.in_(farm_ids))
    if actor.role == "ADMIN":
        query = select(Animal)
    animals = (await session.scalars(query.order_by(Animal.created_at.desc()))).all()
    return [AnimalOut.model_validate(animal) for animal in animals]


@router.get("/animals/{animal_id}", response_model=AnimalOut)
async def get_animal(animal_id: UUID, session: SessionDep, actor: RegistryActor) -> AnimalOut:
    animal = await session.get(Animal, animal_id)
    if animal is None or not await can_manage_farm(session, actor, animal.farm_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "ANIMAL_NOT_FOUND", "message": "Animal not found"},
        )
    return AnimalOut.model_validate(animal)
