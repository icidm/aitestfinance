from datetime import datetime
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from concurrent.futures import ThreadPoolExecutor

from ..db import get_session
from ..auth import require_role
from ..models import User
from ..crud import list_incidents_filtered
from ..pdf import render_pdf, html_to_pdf_bytes

router = APIRouter(tags=["exports"])

# Bounded pool
_pdf_executor = ThreadPoolExecutor(max_workers=2)


@router.get("/api/export/pdf")
async def export_pdf(
    request: Request,
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
    try:
        incidents = await list_incidents_filtered(
            session, status=status, severity=severity, service=service, q=q, days=days
        )
        # services needed for template
        from ..models import Service
        from sqlalchemy import select

        res = await session.execute(select(Service))
        services = res.scalars().all()
        report_lang = "es" if (language or lang).lower().startswith("es") else "en"
        html = render_pdf(incidents, services, lang=report_lang)
        pdf_bytes = await run_in_threadpool(lambda: html_to_pdf_bytes(html))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="incidents_dashboard_{ts}.pdf"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF render failed request_id={getattr(request.state,'request_id','unknown')}: {e}",
        )
