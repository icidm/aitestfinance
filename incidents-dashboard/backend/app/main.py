import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, Query, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session, engine
from .models import Incident, Service, User
from .auth import require_role, get_password_hash
from .crud import compute_stats, compute_timeline, list_incidents_filtered
from .pagination import encode_cursor, decode_cursor, encode_fts_cursor, decode_fts_cursor
from .search import search_incidents_ranked
from .middleware import RequestIdMiddleware
from .logging_config import setup_logging
from .metrics import setup_instrumentator, incident_created_total, incident_resolved_total
from .events import bus
from .routers.auth import router as auth_router
from .routers.stream import router as stream_router
from .routers.exports import router as exports_router
from .routers.reports import router as reports_router

# Setup logging
setup_logging(settings.LOG_LEVEL)

# Validate secret at startup (fail-closed)
if len(settings.SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if not exists (alembic will also handle)
    from .models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed users if not exists
    from .db import async_session_factory

    async with async_session_factory() as session:
        res = await session.execute(select(User).where(User.username == "admin"))
        if not res.scalar_one_or_none():
            for uname, pwd, role in [
                ("viewer", "Viewer123!", "viewer"),
                ("operator", "Operator123!", "operator"),
                ("admin", "Admin123!", "admin"),
            ]:
                u = User(
                    username=uname,
                    hashed_password=get_password_hash(pwd),
                    role=role,
                    is_active=True,
                )
                session.add(u)
            await session.commit()
        # Seed incidents if empty
        res = await session.execute(select(func.count(Incident.id)))
        cnt = res.scalar()
        if cnt == 0:
            from .crud import seed_database

            await seed_database(session)
            await session.commit()
    # Start scheduler
    try:
        from .scheduler import start_scheduler

        # Ensure artifacts dir exists
        os.makedirs(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts"), exist_ok=True
        )
        start_scheduler()
        # Re-add jobs from DB
        async with async_session_factory() as session:
            from .models import ScheduledReportJob

            result = await session.execute(select(ScheduledReportJob))
            jobs = result.scalars().all()
            from .scheduler import add_scheduled_job
            from .routers.reports import _run_scheduled_job_sync

            for j in jobs:
                try:
                    add_scheduled_job(
                        j.id, j.cron, j.interval_seconds, _run_scheduled_job_sync, args=[j.id]
                    )
                except Exception:
                    pass
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"scheduler start failed: {e}")
    yield
    # Dispose
    await engine.dispose()
    try:
        from .scheduler import stop_scheduler

        stop_scheduler()
    except Exception:
        pass


app = FastAPI(
    title="Inditex Incidents Dashboard API",
    version="1.0.0",
    description="PoC API for production incident monitoring",
    lifespan=lifespan,
)

# CORS lockdown
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True if settings.cors_origins_list != ["*"] else False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.add_middleware(RequestIdMiddleware)
setup_instrumentator(app)

app.include_router(auth_router)
app.include_router(stream_router)
app.include_router(exports_router)
app.include_router(reports_router)


# --- Health ---
@app.get("/health", tags=["health"])
async def health(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception:
        raise HTTPException(status_code=503, detail="db unavailable")


# --- Stats ---
@app.get("/api/stats")
async def get_stats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("viewer", "operator", "admin")),
):
    result = await session.execute(select(Incident))
    incidents = result.scalars().all()
    stats = compute_stats(incidents)
    return stats


# --- Incidents list with cursor pagination + FTS ---
@app.get("/api/incidents")
async def get_incidents(
    request: Request,
    status: str | None = Query(None),
    severity: str | None = Query(None),
    service: str | None = Query(None),
    q: str | None = Query(None),
    days: int | None = Query(None, ge=1),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    cursor: str | None = Query(None, description="Opaque pagination cursor"),
    user: User = Depends(require_role("viewer", "operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    # MAX_OFFSET guard for offset compat
    if offset > settings.MAX_OFFSET:
        raise HTTPException(
            status_code=400,
            detail=f"Offset beyond MAX_OFFSET={settings.MAX_OFFSET}; use cursor pagination",
        )
    # If days filter supplied, we need latest-day logic - handled in Python
    # For cursor vs offset branching
    if q:
        # Use search ranked path
        scored = await search_incidents_ranked(
            session, q, status=status, severity=severity, service=service, days=days
        )
        total = len(scored)
        # Cursor handling for rank
        if cursor:
            rank_c, id_c = decode_fts_cursor(cursor)
            # Find position after cursor
            # scored is ORDER BY rank DESC, id ASC
            # predicate (rank,id) < (cursor_rank,cursor_id) per guidance semantics
            filtered = []
            for inc, rank in scored:
                if (rank < rank_c) or (rank == rank_c and inc.id > id_c):
                    # For tie rank == rank_c, need id > cursor_id since ASC
                    filtered.append((inc, rank))
                elif rank < rank_c:
                    filtered.append((inc, rank))
            # Actually need proper logic: since ASC id, we want items where (rank < cursor_rank) OR (rank==cursor_rank AND id > cursor_id)
            # So iterative
            # Recompute correctly
            filtered = []
            for inc, rank in scored:
                if rank < rank_c or (rank == rank_c and inc.id > id_c):
                    filtered.append((inc, rank))
            scored = filtered
        elif offset:
            scored = scored[offset:]
        # limit+1 probe for has_more
        has_more = len(scored) > limit
        page = scored[:limit]
        incidents = [inc for inc, _ in page]
        # next_cursor
        next_cursor = None
        if has_more and page:
            last_inc, last_rank = page[-1]
            next_cursor = encode_fts_cursor(last_rank, last_inc.id)
        # Return shape
        return {
            "total": total,
            "limit": limit,
            "offset": offset if not cursor else 0,
            "incidents": [
                {
                    "id": i.id,
                    "title": i.title,
                    "service": i.service,
                    "severity": i.severity,
                    "status": i.status,
                    "created_at": i.created_at.isoformat(),
                    "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                    "description": i.description,
                }
                for i in incidents
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    else:
        # Non-FTS path: order by created_at DESC, id DESC
        result = await session.execute(
            select(Incident).order_by(Incident.created_at.desc(), Incident.id.desc())
        )
        incidents_all = result.scalars().all()
        # Apply filters
        if status:
            incidents_all = [i for i in incidents_all if i.status == status]
        if severity:
            incidents_all = [i for i in incidents_all if i.severity == severity]
        if service:
            incidents_all = [i for i in incidents_all if i.service == service]
        if days is not None and incidents_all:
            latest = max(i.created_at for i in incidents_all)
            latest_day = latest.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff = latest_day - timedelta(days=days - 1)
            end = latest_day + timedelta(days=1)
            incidents_all = [i for i in incidents_all if cutoff <= i.created_at < end]
        total = len(incidents_all)
        # Cursor predicate
        if cursor:
            c_created, c_id = decode_cursor(cursor)
            filtered = []
            for inc in incidents_all:
                # WHERE (created_at, id) < (cursor_created, cursor_id) for DESC order
                if inc.created_at < c_created or (inc.created_at == c_created and inc.id < c_id):
                    filtered.append(inc)
            incidents_all = filtered
        elif offset:
            incidents_all = incidents_all[offset:]
        has_more = len(incidents_all) > limit
        page = incidents_all[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(last.created_at, last.id)
        # has_more determined via limit+1 logic (we did)
        return {
            "total": total,
            "limit": limit,
            "offset": offset if not cursor else 0,
            "incidents": [
                {
                    "id": i.id,
                    "title": i.title,
                    "service": i.service,
                    "severity": i.severity,
                    "status": i.status,
                    "created_at": i.created_at.isoformat(),
                    "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                    "description": i.description,
                }
                for i in page
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }


# --- Timeline ---
@app.get("/api/incidents/timeline")
async def get_incidents_timeline(
    days: int = Query(14),
    user: User = Depends(require_role("viewer", "operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Incident))
    incidents = result.scalars().all()
    buckets = compute_timeline(incidents, days=days)
    return buckets


# --- Services ---
@app.get("/api/services")
async def get_services(
    user: User = Depends(require_role("viewer", "operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Service))
    services = result.scalars().all()
    result2 = await session.execute(select(Incident))
    incidents = result2.scalars().all()
    out = []
    for svc in services:
        active = sum(
            1 for i in incidents if i.service == svc.name and i.status in ("open", "in_progress")
        )
        out.append(
            {
                "name": svc.name,
                "description": svc.description,
                "status": svc.status,
                "last_checked": svc.last_checked.isoformat(),
                "uptime_7d": svc.uptime_7d,
                "active_incidents": active,
            }
        )
    return out


# --- Resolve ---
@app.put("/api/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: int,
    user: User = Depends(require_role("operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Incident).where(Incident.id == incident_id))
    inc = result.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    inc.status = "resolved"
    inc.resolved_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(inc)
    incident_resolved_total.labels(severity=inc.severity).inc()
    # publish event
    await bus.publish(
        {
            "type": "incident.resolve",
            "incident": {
                "id": inc.id,
                "title": inc.title,
                "service": inc.service,
                "severity": inc.severity,
                "status": inc.status,
                "description": inc.description,
            },
        }
    )
    # also stats
    await bus.publish({"type": "stats", "payload": {}})
    return {
        "ok": True,
        "incident": {
            "id": inc.id,
            "title": inc.title,
            "service": inc.service,
            "severity": inc.severity,
            "status": inc.status,
            "created_at": inc.created_at.isoformat(),
            "resolved_at": inc.resolved_at.isoformat(),
            "description": inc.description,
        },
    }


# --- Create ---
@app.post("/api/incidents", status_code=201)
async def create_incident(
    req: dict,
    user: User = Depends(require_role("operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    title = req.get("title")
    service = req.get("service")
    severity = req.get("severity")
    description = req.get("description", "")
    if not title or not service or not severity:
        raise HTTPException(status_code=400, detail="Missing fields")
    if severity not in ("critical", "high", "medium", "low"):
        raise HTTPException(status_code=400, detail="Invalid severity")
    # Check service exists?
    res = await session.execute(select(Service).where(Service.name == service))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Unknown service")
    # max+1 handled via autoincrement; just create
    inc = Incident(
        title=title,
        service=service,
        severity=severity,
        status="open",
        created_at=datetime.now(timezone.utc),
        resolved_at=None,
        description=description,
    )
    session.add(inc)
    await session.commit()
    await session.refresh(inc)
    incident_created_total.labels(severity=severity).inc()
    await bus.publish(
        {
            "type": "incident.create",
            "incident": {
                "id": inc.id,
                "title": inc.title,
                "service": inc.service,
                "severity": inc.severity,
                "status": inc.status,
                "description": inc.description,
            },
        }
    )
    await bus.publish({"type": "stats", "payload": {}})
    # Structured log with user_id
    import logging

    logging.getLogger("app").info(
        f"incident created id={inc.id} user_id={user.username} endpoint=/api/incidents"
    )
    return {
        "id": inc.id,
        "title": inc.title,
        "service": inc.service,
        "severity": inc.severity,
        "status": inc.status,
        "created_at": inc.created_at.isoformat(),
        "resolved_at": None,
        "description": inc.description,
    }


# --- Reset ---
@app.post("/api/reset")
async def reset_data(
    user: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_session)
):
    from .crud import seed_database

    await seed_database(session)
    await session.commit()
    return {"ok": True, "message": "Data reset to seed state"}


# --- PPTX export (preserve original logic but async DB) ---
@app.get("/api/export/pptx")
async def export_pptx(
    status: str | None = Query(None),
    severity: str | None = Query(None),
    service: str | None = Query(None),
    q: str | None = Query(None),
    days: int | None = Query(None, ge=1),
    lang: str = Query("en"),
    language: str | None = Query(None),
    user: User = Depends(require_role("viewer", "operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    incidents = await list_incidents_filtered(
        session, status=status, severity=severity, service=service, q=q, days=days
    )
    # Convert to dict style expected by _build_pptx
    inc_dicts = [
        {
            "id": i.id,
            "title": i.title,
            "service": i.service,
            "severity": i.severity,
            "status": i.status,
            "created_at": i.created_at.isoformat(),
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            "description": i.description,
        }
        for i in incidents
    ]
    result = await session.execute(select(Service))
    services = result.scalars().all()
    svc_dicts = [{"name": s.name, "description": s.description} for s in services]
    # Import original _build_pptx from legacy main's logic - reuse file's function
    # For now, import from parent main's backup or replicate minimal
    # We'll dynamically import the original pptx builder from ../main.py's function if exists
    import io

    # Use app.pdf's logic? Instead replicate call to original builder located in ../../main.py backup
    # Simpler: reuse python-pptx builder via same code as legacy - copy function here
    from .pptx_builder import build_pptx

    selected_lang = language or lang
    report_lang = "es" if (selected_lang or "").lower().startswith("es") else "en"
    prs = build_pptx(inc_dicts, svc_dicts, report_lang)
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="incidents_dashboard_{ts}.pptx"'},
    )


# Mount frontend static after API routes
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/dashboard", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/dashboard/")
