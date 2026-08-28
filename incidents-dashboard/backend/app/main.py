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
    # Robust startup: ensure tables exist before seed — alembic upgrade head via sync_engine or fallback to Base.metadata.create_all
    # Handles fresh sqlite app.db (0 bytes) when alembic only in docker entrypoint, plus postgres path, plus async session creation.
    from .models import Base
    import logging as _logging

    _log = _logging.getLogger(__name__)
    # 1) Attempt alembic upgrade head via sync_engine; fallback to create_all (async + sync) — covers both postgres and sqlite
    _tables_ready = False
    try:
        import os as _os
        from sqlalchemy import create_engine as _create_engine, text as _text
        from alembic.config import Config as _AlembicConfig
        from alembic import command as _alembic_command

        _sync_url = _os.getenv("DATABASE_URL_SYNC", settings.DATABASE_URL_SYNC)
        # Resolve alembic.ini robustly — handles CWD variations (docker /app vs local python vs tests)
        _candidates = [
            _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "alembic.ini")),
            _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "alembic.ini"),
            _os.path.join(_os.getcwd(), "incidents-dashboard/backend/alembic.ini"),
            _os.path.join(_os.getcwd(), "alembic.ini"),
            "alembic.ini",
        ]
        _alembic_ini = next((p for p in _candidates if _os.path.exists(p)), _candidates[0])
        if _os.path.exists(_alembic_ini):
            _cfg = _AlembicConfig(_alembic_ini)
            _cfg.set_main_option("sqlalchemy.url", _sync_url)
            # Ensure script_location resolves absolute (alembic.ini uses relative 'alembic')
            _script_loc = _cfg.get_main_option("script_location") or "alembic"
            if not _os.path.isabs(_script_loc):
                _abs_script = _os.path.join(_os.path.dirname(_os.path.abspath(_alembic_ini)), _script_loc)
                if _os.path.exists(_abs_script):
                    _cfg.set_main_option("script_location", _abs_script)
            # Validate sync engine connectivity before alembic (creates sqlite file if missing)
            _sync_kwargs = {"pool_pre_ping": True}
            if _sync_url.startswith("sqlite"):
                _sync_kwargs["connect_args"] = {"check_same_thread": False}
            _sync_engine = _create_engine(_sync_url, **_sync_kwargs)
            try:
                with _sync_engine.connect() as _conn:
                    _conn.execute(_text("SELECT 1"))
                _alembic_command.upgrade(_cfg, "head")
                _log.info("alembic upgrade head succeeded via sync_engine")
                _tables_ready = True
            finally:
                _sync_engine.dispose()
        else:
            raise FileNotFoundError(f"alembic.ini not found at {_alembic_ini}")
    except Exception as _e:
        _log.warning(f"alembic upgrade head failed ({_e}), falling back to Base.metadata.create_all")
    if not _tables_ready:
        # Fallback: async create_all (primary) then sync create_all (secondary) for sqlite file creation edge
        try:
            async with engine.begin() as _conn:
                await _conn.run_sync(Base.metadata.create_all)
            _log.info("async Base.metadata.create_all succeeded")
            _tables_ready = True
        except Exception as _e2:
            _log.warning(f"async create_all failed ({_e2}), trying sync create_all")
            try:
                import os as _os2
                from sqlalchemy import create_engine as _ce2

                _sync_url2 = _os2.getenv("DATABASE_URL_SYNC", settings.DATABASE_URL_SYNC)
                _sync_kwargs2 = {}
                if _sync_url2.startswith("sqlite"):
                    _sync_kwargs2["connect_args"] = {"check_same_thread": False}
                _se2 = _ce2(_sync_url2, **_sync_kwargs2)
                Base.metadata.create_all(bind=_se2)
                _se2.dispose()
                _log.info("sync Base.metadata.create_all succeeded")
                _tables_ready = True
            except Exception as _e3:
                _log.error(f"all table creation attempts failed: {_e3}")
    # 2) Idempotent seed with injectable clock and hardened async session creation — ensures viewer/Viewer123! etc. exist
    from .db import async_session_factory
    from datetime import datetime as _dt, timezone as _tz

    # Injectable clock: default now, overridable via env/SEED_CLOCK or caller injection for determinism (seed 42)
    def _default_clock():
        return _dt.now(_tz.utc)

    _seed_clock = _default_clock
    # If crud.seed_database supports clock param, we pass _seed_clock explicitly for test determinism
    # First, ensure users exist in isolated session with proper commit/rollback handling
    async with async_session_factory() as session:
        try:
            res = await session.execute(select(User).where(User.username == "admin"))
            if not res.scalar_one_or_none():
                for uname, pwd, role in [
                    ("viewer", "Viewer123!", "viewer"),
                    ("operator", "Operator123!", "operator"),
                    ("admin", "Admin123!", "admin"),
                ]:
                    try:
                        hashed = get_password_hash(pwd)
                    except Exception as e:
                        _log.error(f"hash failed for {uname}: {e}")
                        import bcrypt

                        hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
                    u = User(
                        username=uname,
                        hashed_password=hashed,
                        role=role,
                        is_active=True,
                    )
                    session.add(u)
                await session.commit()
                _log.info("seeded users viewer/operator/admin")
            else:
                _log.info("users already seeded, skipping")
        except Exception as e:
            _log.warning(f"user seed skipped: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
    # 3) Seed incidents if empty — separate async session to avoid mixing user-seed transaction state, injectable clock for determinism
    async with async_session_factory() as session:
        try:
            res = await session.execute(select(func.count(Incident.id)))
            cnt = res.scalar()
            if cnt == 0:
                from .crud import seed_database

                await seed_database(session, clock=_seed_clock)
                await session.commit()
                _log.info(f"seeded incidents via seed_database clock={_seed_clock.__name__}")
            else:
                _log.info(f"incidents already present cnt={cnt}, skipping seed")
        except Exception as e:
            _log.warning(f"incident seed skipped: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
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
