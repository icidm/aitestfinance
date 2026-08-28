from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: str | None = None
    role: str | None = None
    jti: str | None = None
    type: str | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool


class UserCreate(BaseModel):
    username: str
    password: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateIncidentRequest(BaseModel):
    title: str
    service: str
    severity: str
    description: str = ""


class IncidentOut(BaseModel):
    id: int
    title: str
    service: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    description: str


class StatsOut(BaseModel):
    total_incidents: int
    open_incidents: int
    resolved_incidents: int
    critical_open: int
    mttr_minutes: Optional[float] = None
    by_severity: dict
    by_status: dict


class ServiceOut(BaseModel):
    name: str
    description: str
    status: str
    last_checked: datetime
    uptime_7d: float
    active_incidents: int = 0


class ScheduleRequest(BaseModel):
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    filters: Optional[dict] = None
    lang: str = "en"


class JobOut(BaseModel):
    id: str
    cron: Optional[str]
    interval_seconds: Optional[int]
    filters: Optional[dict]
    created_by: Optional[int]
    created_at: datetime
    next_run_time: Optional[datetime]
    last_run_at: Optional[datetime]
    last_status: Optional[str]
