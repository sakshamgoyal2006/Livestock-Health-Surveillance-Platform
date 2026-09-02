from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps import require_roles
from app.api.routes.media import sanitize_image
from app.domain.models import User
from app.main import app


@pytest.mark.asyncio
async def test_health_and_request_id_without_database() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "unit-health-1"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "unit-health-1"


@pytest.mark.asyncio
async def test_validation_uses_consistent_error_envelope() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/dev-login",
            json={"email": "invalid", "role": "FARMER", "password": "dev-only"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["request_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("FARMER", False),
        ("FIELD_WORKER", False),
        ("VETERINARIAN", True),
        ("DISTRICT_OFFICER", False),
        ("ADMIN", True),
    ],
)
async def test_role_dependency_matrix(role: str, allowed: bool) -> None:
    user = User(
        email=f"{role.lower()}@example.com",
        display_name="Synthetic role test",
        role=role,
        active=True,
        synthetic=True,
    )
    dependency = require_roles("VETERINARIAN", "ADMIN")
    if allowed:
        assert await dependency(user) is user
    else:
        with pytest.raises(HTTPException) as error:
            await dependency(user)
        assert error.value.status_code == 403


def test_image_sanitization_removes_exif() -> None:
    original = BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "synthetic metadata"
    Image.new("RGB", (8, 8), color=(15, 80, 65)).save(original, format="JPEG", exif=exif)
    sanitized = sanitize_image(original.getvalue(), "image/jpeg")
    with Image.open(BytesIO(sanitized)) as image:
        assert len(image.getexif()) == 0


def test_image_sanitization_rejects_non_image() -> None:
    with pytest.raises(HTTPException) as error:
        sanitize_image(b"not-an-image", "image/jpeg")
    assert error.value.status_code == 422
