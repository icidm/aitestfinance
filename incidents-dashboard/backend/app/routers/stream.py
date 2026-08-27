import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_role
from ..models import User
from ..events import bus, sse_format, matches_filters
from ..metrics import sse_connections_active, sse_events_total
from ..db import get_session

router = APIRouter(tags=["stream"])


async def event_generator(request: Request, query_params: dict, user: User):
    queue = bus.subscribe()
    sse_connections_active.inc()
    try:
        # Replay if Last-Event-ID provided
        last_event_id = request.headers.get("Last-Event-ID")
        if last_event_id:
            for ev in bus.since(last_event_id):
                if matches_filters(ev, query_params):
                    yield sse_format(ev)
                    sse_events_total.inc()
        while True:
            if await request.is_disconnected():
                break
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                if not matches_filters(ev, query_params):
                    continue
                yield sse_format(ev)
                sse_events_total.inc()
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
            except asyncio.CancelledError:
                break
    except asyncio.CancelledError:
        pass
    finally:
        bus.unsubscribe(queue)
        sse_connections_active.dec()


@router.get("/api/incidents/stream")
async def incidents_stream(
    request: Request,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    service: Optional[str] = None,
    q: Optional[str] = None,
    user: User = Depends(require_role("viewer", "operator", "admin")),
):
    params = {"status": status, "severity": severity, "service": service, "q": q}
    # Remove None
    params = {k: v for k, v in params.items() if v is not None}
    generator = event_generator(request, params, user)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/stats/stream")
async def stats_stream(
    request: Request,
    user: User = Depends(require_role("viewer", "operator", "admin")),
    session: AsyncSession = Depends(get_session),
):
    # Similar to incidents but emits stats periodically; reuse same bus but filter type
    async def stats_gen():
        queue = bus.subscribe()
        sse_connections_active.inc()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                    # For stats stream, recompute stats or forward incident events as stats
                    if ev.get("type") in ("incident.create", "incident.resolve", "stats"):
                        # Emit stats delta
                        yield sse_format({"type": "stats", "seq": ev.get("seq"), "data": ev})
                        sse_events_total.inc()
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            bus.unsubscribe(queue)
            sse_connections_active.dec()

    return StreamingResponse(
        stats_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
