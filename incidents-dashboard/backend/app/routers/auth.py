from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..auth import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    blacklist_jti,
    get_current_user,
)
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=401, detail="Inactive user", headers={"WWW-Authenticate": "Bearer"}
        )
    access = create_access_token({"sub": user.username, "role": user.role})
    refresh = create_refresh_token({"sub": user.username, "role": user.role})
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/refresh")
async def refresh(body: dict, session: AsyncSession = Depends(get_session)):
    token = body.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=401, detail="Missing refresh_token", headers={"WWW-Authenticate": "Bearer"}
        )
    payload = await decode_refresh_token(token, session)
    jti = payload["jti"]
    username = payload["sub"]
    role = payload.get("role")
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    # Blacklist old jti
    await blacklist_jti(session, jti, exp)
    # Issue new pair
    new_access = create_access_token({"sub": username, "role": role})
    new_refresh = create_refresh_token({"sub": username, "role": role})
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role, "id": user.id}
