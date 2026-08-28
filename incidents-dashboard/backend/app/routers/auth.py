from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
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
async def login(request: Request, session: AsyncSession = Depends(get_session)):
    # Support both application/x-www-form-urlencoded (OAuth2PasswordRequestForm) and application/json
    # to avoid 500/422 when frontend sends JSON vs form. Preserves JWT jti rotation and RBAC.
    content_type = request.headers.get("content-type", "")
    username = None
    password = None
    try:
        if "application/json" in content_type:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        else:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
            # Fallback: if form empty, try JSON body (some clients omit content-type)
            if not username and not password:
                try:
                    body = await request.json()
                    username = body.get("username") or username
                    password = body.get("password") or password
                except Exception:
                    pass
    except Exception:
        raise HTTPException(
            status_code=422,
            detail="Missing username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not username or not password:
        raise HTTPException(
            status_code=422,
            detail="Missing username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=500, detail="Database error during login")
    # verify_password is hardened to never throw 500 (catches UnknownHashError/ValueError -> 401)
    try:
        pwd_ok = verify_password(password, user.hashed_password) if user else False
    except Exception:
        pwd_ok = False
    if not user or not pwd_ok:
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
