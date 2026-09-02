from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.adapters.identity import DevelopmentIdentityAdapter
from app.api.deps import CurrentUser, SessionDep, SettingsDep
from app.core.security import create_access_token
from app.schemas.auth import DevLoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/v1", tags=["authentication"])


@router.post("/auth/dev-login", response_model=TokenResponse)
async def dev_login(
    body: DevLoginRequest, session: SessionDep, settings: SettingsDep
) -> TokenResponse:
    if not settings.dev_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DEV_AUTH_DISABLED", "message": "Development login is disabled"},
        )
    user = await DevelopmentIdentityAdapter().authenticate(
        session=session,
        email=str(body.email),
        role=body.role,
        password=body.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_DEV_LOGIN", "message": "Email, role, or password is invalid"},
        )
    return TokenResponse(
        access_token=create_access_token(user_id=user.id, role=user.role, settings=settings),
        expires_in=settings.access_token_ttl_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
