from datetime import datetime, timedelta, timezone
import uuid

from jose import jwt, JWTError

# bcrypt 4.x compatibility shim for passlib
try:
    import bcrypt

    if not hasattr(bcrypt, "__about__"):
        bcrypt.__about__ = type(
            "obj", (object,), {"__version__": getattr(bcrypt, "__version__", "4.0.0")}
        )()
except Exception:
    pass
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import User, TokenBlacklist

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

ALGORITHM = "HS256"


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
            "type": "access",
        }
    )
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
            "type": "refresh",
        }
    )
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        jti: str = payload.get("jti")
        typ: str = payload.get("type")
        if username is None or jti is None:
            raise credentials_exception
        if typ != "access":
            raise credentials_exception
        # Check blacklist for jti? access tokens not blacklisted but check anyway
        res = await session.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
        if res.scalar_one_or_none():
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    # Load user
    res = await session.execute(select(User).where(User.username == username))
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*roles: str):
    async def _dep(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Forbidden: insufficient role")
        return user

    return _dep


async def decode_refresh_token(token: str, session: AsyncSession):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401, detail="Invalid token type", headers={"WWW-Authenticate": "Bearer"}
            )
        jti = payload.get("jti")
        username = payload.get("sub")
        if not jti or not username:
            raise HTTPException(
                status_code=401, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"}
            )
        # check blacklist
        res = await session.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
        if res.scalar_one_or_none():
            raise HTTPException(
                status_code=401,
                detail="Refresh token revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=401, detail="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"}
        )


async def blacklist_jti(session: AsyncSession, jti: str, exp: datetime):
    bl = TokenBlacklist(jti=jti, expires_at=exp)
    session.add(bl)
    await session.commit()
