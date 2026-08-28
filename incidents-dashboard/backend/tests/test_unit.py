import base64, json
from datetime import datetime, timezone

def test_pagination_encode_decode():
    from app.pagination import encode_cursor, decode_cursor, encode_fts_cursor, decode_fts_cursor
    dt = datetime.now(timezone.utc)
    c = encode_cursor(dt, 123)
    dt2, id2 = decode_cursor(c)
    assert id2 == 123
    # Invalid cursor
    try:
        decode_cursor("invalid")
        assert False
    except Exception as e:
        assert e.status_code == 400
    # FTS
    fc = encode_fts_cursor(1.5, 42)
    r, i = decode_fts_cursor(fc)
    assert r == 1.5 and i == 42

def test_pagination_max_offset():
    from app.pagination import MAX_OFFSET
    assert MAX_OFFSET == 10000

def test_search_rank():
    from app.search import normalize_q, q_matches, rank_for_q
    from app.models import Incident
    from datetime import datetime, timezone
    inc = Incident(id=1, title="Payment error", service="Zara-API", severity="high", status="open", created_at=datetime.now(timezone.utc), description="desc payment", search_vector=None)
    assert q_matches(inc, "payment")
    assert normalize_q(" Payment ") == "payment"
    assert rank_for_q(inc, "payment") > 0

def test_events_bus():
    import asyncio
    from app.events import bus, sse_format, matches_filters
    # Test matches_filters
    event = {"incident": {"id":1, "title":"Payment", "service":"Zara-API","severity":"critical","status":"open","description":"pay"}}
    assert matches_filters(event, {"severity":"critical"}) is True
    assert matches_filters(event, {"severity":"low"}) is False
    assert matches_filters(event, {"q":"payment"}) is True
    assert matches_filters(event, {"q":"nomatch"}) is False
    # sse_format
    fmt = sse_format({"seq":5, "type":"test"})
    assert "id: 5" in fmt

def test_metrics_labels():
    from app.metrics import incident_created_total, incident_resolved_total, sse_connections_active
    incident_created_total.labels(severity="critical").inc()
    incident_resolved_total.labels(severity="high").inc()
    sse_connections_active.set(1)
    assert True

def test_logging_config():
    from app.logging_config import setup_logging
    setup_logging("INFO")
    import logging
    logging.getLogger("test").info("test log request_id test", extra={"endpoint":"/test","user_id":"user1"})

def test_pdf_render():
    from app.pdf import render_pdf, html_to_pdf_bytes
    from datetime import datetime, timezone
    from app.models import Incident, Service
    incidents = [
        Incident(id=1, title="Test", service="Zara-API", severity="critical", status="open", created_at=datetime.now(timezone.utc), description="desc", search_vector=None),
        Incident(id=2, title="Another", service="IOP-Gateway", severity="low", status="resolved", created_at=datetime.now(timezone.utc), resolved_at=datetime.now(timezone.utc), description="desc2", search_vector=None),
    ]
    services = [Service(name="Zara-API", description="desc", status="healthy", last_checked=datetime.now(timezone.utc), uptime_7d=99.5)]
    html = render_pdf(incidents, services, lang="en")
    assert "Incident Dashboard" in html
    pdf = html_to_pdf_bytes(html)
    assert len(pdf) > 1000
    # es
    html2 = render_pdf(incidents, services, lang="es")
    assert "Panel" in html2

def test_artifact_store():
    from app.artifact_store import save_artifact, get_artifact_path
    import os
    data = b"test pdf data " * 200
    path = save_artifact("test-job", data)
    assert os.path.exists(path)
    got = get_artifact_path("test-job")
    assert got == path or os.path.exists(got)
    # cleanup
    import shutil
    shutil.rmtree(os.path.join(os.path.dirname(path), "..", "test-job"), ignore_errors=True)
    # Actually remove
    try:
        os.remove(path)
        os.rmdir(os.path.dirname(path))
    except:
        pass

def test_crud_helpers():
    from app.crud import compute_stats, compute_timeline, generate_data
    from datetime import datetime, timezone
    clock = lambda: datetime(2026,1,15, tzinfo=timezone.utc)
    incs, svcs = generate_data(clock)
    # Convert to model-like objects for compute
    from app.models import Incident
    incidents = [Incident(id=i["id"], title=i["title"], service=i["service"], severity=i["severity"], status=i["status"], created_at=i["created_at"], resolved_at=i["resolved_at"], description=i["description"]) for i in incs]
    stats = compute_stats(incidents)
    assert "total_incidents" in stats
    tl = compute_timeline(incidents, days=14)
    assert isinstance(tl, list)

def test_config():
    from app.config import settings
    assert settings.MAX_OFFSET == 10000
    assert len(settings.SECRET_KEY) >= 32
    assert "http" in settings.cors_origins_list[0]

def test_scheduler_memory():
    from app.scheduler import get_scheduler, add_scheduled_job, remove_job
    sched = get_scheduler()
    # Add dummy job
    def dummy():
        pass
    job = add_scheduled_job("unit-test-job", "0 8 * * *", None, dummy, args=[])
    assert job is not None
    remove_job("unit-test-job")

def test_middleware_request_id():
    from app.middleware import RequestIdMiddleware
    assert RequestIdMiddleware is not None

def test_auth_helpers():
    from app.auth import get_password_hash, verify_password, create_access_token, create_refresh_token
    h = get_password_hash("test123")
    assert verify_password("test123", h)
    tok = create_access_token({"sub":"user","role":"viewer"})
    assert isinstance(tok, str)
    ref = create_refresh_token({"sub":"user","role":"viewer"})
    assert isinstance(ref, str)
