import json
import uuid
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..auth import require_role
from ..models import User, ScheduledReportJob, JobRun
from ..scheduler import add_scheduled_job, remove_job
from ..pdf import render_pdf, html_to_pdf_bytes
from ..crud import list_incidents_filtered
from ..artifact_store import save_artifact, get_artifact_path

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _run_scheduled_job_sync(job_id: str):
    # This runs in scheduler thread; need to handle async internally via new loop
    import asyncio
    from ..db import async_session_factory
    from ..models import ScheduledReportJob, JobRun, Service
    from sqlalchemy import select

    async def _inner():
        async with async_session_factory() as session:
            result = await session.execute(
                select(ScheduledReportJob).where(ScheduledReportJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if not job:
                return
            filters = json.loads(job.filters) if job.filters else {}
            try:
                incidents = await list_incidents_filtered(
                    session,
                    status=filters.get("status"),
                    severity=filters.get("severity"),
                    service=filters.get("service"),
                    q=filters.get("q"),
                    days=filters.get("days"),
                )
                res = await session.execute(select(Service))
                services = res.scalars().all()
                lang = filters.get("lang", "en")
                html = render_pdf(incidents, services, lang=lang)
                pdf_bytes = html_to_pdf_bytes(html)
                path = save_artifact(job_id, pdf_bytes)
                run = JobRun(
                    job_id=job_id,
                    status="success",
                    artifact_path=path,
                    request_id=str(uuid.uuid4()),
                )
                session.add(run)
                job.last_run_at = datetime.now(timezone.utc)
                job.last_status = "success"
                job.next_run_time = None  # APScheduler manages
                await session.commit()
                # publish event
                try:
                    from ..events import bus

                    await bus.publish(
                        {"type": "report.generated", "job_id": job_id, "artifact": path}
                    )
                except Exception:
                    pass
            except Exception as e:
                run = JobRun(
                    job_id=job_id, status="failed", error=str(e), request_id=str(uuid.uuid4())
                )
                session.add(run)
                job.last_run_at = datetime.now(timezone.utc)
                job.last_status = "failed"
                await session.commit()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_inner())
        loop.close()
    except Exception:
        pass


@router.post("/schedule")
async def schedule_report(
    body: dict,
    user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    cron = body.get("cron")
    interval = body.get("interval_seconds")
    filters = body.get("filters", {})
    if not cron and not interval:
        raise HTTPException(status_code=400, detail="cron or interval_seconds required")
    job_id = str(uuid.uuid4())
    job = ScheduledReportJob(
        id=job_id,
        cron=cron,
        interval_seconds=interval,
        filters=json.dumps(filters) if filters else None,
        created_by=user.id,
    )
    session.add(job)
    await session.commit()
    try:
        # Ensure scheduler is running for tenant
        from ..scheduler import get_scheduler, start_scheduler

        try:
            start_scheduler()
        except Exception:
            pass
        add_scheduled_job(job_id, cron, interval, _run_scheduled_job_sync, args=[job_id])
        # compute next_run_time via scheduler
        sched = get_scheduler()
        j = sched.get_job(job_id)
        nxt = getattr(j, "next_run_time", None) if j else None
        if nxt:
            job.next_run_time = nxt
            await session.commit()
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except AttributeError:
        # Scheduler tentatively added, ignore
        pass
    return {
        "id": job_id,
        "cron": cron,
        "interval_seconds": interval,
        "filters": filters,
        "next_run_time": job.next_run_time,
    }


@router.get("/jobs")
async def list_jobs(
    user: User = Depends(require_role("admin")), session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(ScheduledReportJob))
    jobs = result.scalars().all()
    out = []
    for j in jobs:
        out.append(
            {
                "id": j.id,
                "cron": j.cron,
                "interval_seconds": j.interval_seconds,
                "filters": json.loads(j.filters) if j.filters else {},
                "created_by": j.created_by,
                "created_at": j.created_at,
                "next_run_time": j.next_run_time,
                "last_run_at": j.last_run_at,
                "last_status": j.last_status,
            }
        )
    return out


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ScheduledReportJob).where(ScheduledReportJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await session.execute(delete(JobRun).where(JobRun.job_id == job_id))
    await session.delete(job)
    await session.commit()
    remove_job(job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/run")
async def run_job_now(
    job_id: str,
    user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ScheduledReportJob).where(ScheduledReportJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _run_scheduled_job_sync(job_id)
    return {"ok": True}


@router.get("/jobs/{job_id}/artifact")
async def get_artifact(job_id: str, user: User = Depends(require_role("admin"))):
    path = get_artifact_path(job_id)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Artifact not found")

    def iterfile():
        with open(path, "rb") as f:
            yield from f

    return StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(path)}"'},
    )


@router.get("/jobs/{job_id}/runs")
async def list_runs(
    job_id: str,
    user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.run_at.desc())
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "job_id": r.job_id,
            "run_at": r.run_at,
            "status": r.status,
            "artifact_path": r.artifact_path,
            "error": r.error,
            "request_id": r.request_id,
        }
        for r in runs
    ]
