from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import APIModel

SpeciesValue = Literal["CATTLE", "BUFFALO"]
PrecisionValue = Literal["EXACT", "APPROXIMATE", "VILLAGE_ONLY"]


class CoordinatesMixin(APIModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_precision: PrecisionValue = "VILLAGE_ONLY"

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> CoordinatesMixin:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if self.location_precision == "EXACT" and self.latitude is None:
            raise ValueError("exact location precision requires coordinates")
        return self


class FarmCreate(CoordinatesMixin):
    id: UUID
    name: str = Field(min_length=1, max_length=120)
    village_name: str = Field(min_length=1, max_length=120)


class FarmOut(APIModel):
    id: UUID
    owner_user_id: UUID
    name: str
    village_name: str
    latitude: float | None
    longitude: float | None
    location_precision: str
    version: int
    created_at: datetime


class HerdCreate(APIModel):
    id: UUID
    farm_id: UUID
    name: str = Field(min_length=1, max_length=120)
    species: SpeciesValue
    animal_count: int = Field(ge=1, le=100000)


class HerdOut(APIModel):
    id: UUID
    farm_id: UUID
    name: str
    species: SpeciesValue
    animal_count: int
    version: int
    created_at: datetime


class AnimalCreate(APIModel):
    id: UUID
    farm_id: UUID
    herd_id: UUID | None = None
    tag_number: str = Field(min_length=1, max_length=80)
    species: SpeciesValue
    sex: Literal["FEMALE", "MALE", "UNKNOWN"]
    age_band: Literal["CALF", "YOUNG", "ADULT", "UNKNOWN"]


class AnimalOut(APIModel):
    id: UUID
    farm_id: UUID
    herd_id: UUID | None
    tag_number: str
    species: SpeciesValue
    sex: str
    age_band: str
    version: int
    created_at: datetime
