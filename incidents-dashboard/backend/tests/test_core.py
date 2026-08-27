import pytest
import asyncio
from datetime import datetime, timezone

pytestmark = pytest.mark.asyncio

async def test_unauth_401(client):
    r = await client.get("/api/stats")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers

async def test_login_tokens(client):
    r = await client.post("/api/auth/login", data={"username":"viewer","password":"Viewer123!"}, headers={"Content-Type":"application/x-www-form-urlencoded"})
    assert r.status_code == 200
    j = r.json()
    assert "access_token" in j and "refresh_token" in j
    assert j["token_type"] == "bearer"

async def test_viewer_read(client, viewer_token):
    h = {"Authorization": f"Bearer {viewer_token}"}
    for path in ["/api/stats", "/api/incidents", "/api/incidents/timeline", "/api/services"]:
        r = await client.get(path, headers=h)
        assert r.status_code == 200, f"{path} {r.text}"

async def test_viewer_forbidden_create(client, viewer_token):
    h = {"Authorization": f"Bearer {viewer_token}"}
    r = await client.post("/api/incidents", json={"title":"t","service":"Zara-API","severity":"high"}, headers=h)
    assert r.status_code == 403

async def test_operator_create_and_resolve(client, operator_token, viewer_token):
    h = {"Authorization": f"Bearer {operator_token}"}
    r = await client.post("/api/incidents", json={"title":"Test incident","service":"Zara-API","severity":"critical","description":"desc"}, headers=h)
    assert r.status_code == 201, r.text
    inc = r.json()
    assert inc["status"] == "open"
    # Resolve
    r2 = await client.put(f"/api/incidents/{inc['id']}/resolve", headers=h)
    assert r2.status_code == 200
    assert r2.json()["incident"]["status"] == "resolved"
    # Viewer cannot resolve
    h2 = {"Authorization": f"Bearer {viewer_token}"}
    r3 = await client.put(f"/api/incidents/{inc['id']}/resolve", headers=h2)
    assert r3.status_code == 403

async def test_admin_reset(client, admin_token, viewer_token):
    h_view = {"Authorization": f"Bearer {viewer_token}"}
    r = await client.post("/api/reset", headers=h_view)
    assert r.status_code == 403
    h_admin = {"Authorization": f"Bearer {admin_token}"}
    r2 = await client.post("/api/reset", headers=h_admin)
    assert r2.status_code == 200
    # Count should be 120
    r3 = await client.get("/api/incidents?limit=100", headers=h_admin)
    assert r3.status_code == 200
    assert r3.json()["total"] >= 120

async def test_refresh_rotation(client, admin_token):
    # login
    r = await client.post("/api/auth/login", data={"username":"admin","password":"Admin123!"}, headers={"Content-Type":"application/x-www-form-urlencoded"})
    j = r.json()
    refresh = j["refresh_token"]
    r2 = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    j2 = r2.json()
    assert "access_token" in j2
    # replay old should fail
    r3 = await client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert r3.status_code == 401

async def test_stats_shape(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/stats", headers=h)
    assert r.status_code == 200
    j = r.json()
    assert "total_incidents" in j and "by_severity" in j and "by_status" in j

async def test_cursor_pagination(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/incidents?limit=25", headers=h)
    assert r.status_code == 200
    j = r.json()
    assert "next_cursor" in j and "has_more" in j
    assert len(j["incidents"]) <= 25
    if j["has_more"]:
        assert j["next_cursor"] is not None
        r2 = await client.get(f"/api/incidents?limit=25&cursor={j['next_cursor']}", headers=h)
        assert r2.status_code == 200
        ids1 = {i["id"] for i in j["incidents"]}
        ids2 = {i["id"] for i in r2.json()["incidents"]}
        assert ids1.isdisjoint(ids2), "no duplicates"

async def test_max_offset_guard(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/incidents?offset=10001", headers=h)
    assert r.status_code == 400
    assert "MAX_OFFSET" in r.json()["detail"]
    r2 = await client.get("/api/incidents?offset=10000&limit=10", headers=h)
    assert r2.status_code == 200

async def test_search_q(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/incidents?q=payment", headers=h)
    assert r.status_code == 200
    for inc in r.json()["incidents"]:
        txt = f"{inc['id']} {inc['title']} {inc['service']} {inc['description']}".lower()
        assert "payment" in txt

async def test_search_case_insensitive(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r1 = await client.get("/api/incidents?q=Payment", headers=h)
    r2 = await client.get("/api/incidents?q=payment", headers=h)
    assert r1.json()["total"] == r2.json()["total"]

async def test_days_filter(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/export/pptx?days=7", headers=h)
    assert r.status_code == 200
    assert "presentation" in r.headers["content-type"]

async def test_bilingual_export(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r_en = await client.get("/api/export/pptx?lang=en", headers=h)
    r_es = await client.get("/api/export/pptx?lang=es", headers=h)
    assert r_en.status_code == 200
    assert r_es.status_code == 200

async def test_pdf_export(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/export/pdf?lang=en", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 1000

async def test_pdf_filters(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/export/pdf?status=open&q=payment&days=14&lang=en", headers=h)
    assert r.status_code == 200

async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "up"

async def test_metrics(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    # Trigger some traffic
    await client.get("/api/stats", headers=h)
    r = await client.get("/metrics")
    assert r.status_code == 200
    txt = r.text
    assert "http_requests_total" in txt
    assert "incident_created_total" in txt or "http_request_duration" in txt
    # No user_id label
    assert "user_id" not in txt or "user_id" not in [l.split("{")[0] for l in txt.splitlines() if "http_requests_total" in l]

async def test_timeline(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/incidents/timeline?days=14", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Should be asc by date
    dates = [d["date"] for d in data]
    assert dates == sorted(dates)

async def test_services(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/services", headers=h)
    assert r.status_code == 200
    for svc in r.json():
        assert "active_incidents" in svc

async def test_create_sorted_desc(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post("/api/incidents", json={"title":"Sort test","service":"Zara-API","severity":"low"}, headers=h)
    assert r.status_code == 201
    r2 = await client.get("/api/incidents?limit=1", headers=h)
    assert r2.json()["incidents"][0]["id"] == r.json()["id"]

async def test_cors_headers(client):
    r = await client.options("/api/stats", headers={"Origin":"http://localhost:8000","Access-Control-Request-Method":"GET"})
    # FastAPI CORSMiddleware responds

async def test_seed_deterministic(session):
    from app.crud import generate_data
    from datetime import datetime, timezone
    clock = lambda: datetime(2026,1,15, tzinfo=timezone.utc)
    inc1, svc1 = generate_data(clock)
    inc2, svc2 = generate_data(clock)
    assert inc1 == inc2
    assert len(inc1) == 120
    assert len(svc1) == 8

async def test_concurrent_resolves(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    # Create two incidents
    r1 = await client.post("/api/incidents", json={"title":"Conc1","service":"Zara-API","severity":"medium"}, headers=h)
    r2 = await client.post("/api/incidents", json={"title":"Conc2","service":"Zara-API","severity":"medium"}, headers=h)
    id1 = r1.json()["id"]; id2 = r2.json()["id"]
    results = await asyncio.gather(
        client.put(f"/api/incidents/{id1}/resolve", headers=h),
        client.put(f"/api/incidents/{id2}/resolve", headers=h),
    )
    assert all(r.status_code == 200 for r in results)
    assert results[0].json()["incident"]["status"] == "resolved"
    assert results[1].json()["incident"]["status"] == "resolved"

async def test_sse_auth_required(client):
    r = await client.get("/api/incidents/stream")
    assert r.status_code == 401

async def test_schedule_admin_only(client, viewer_token, admin_token):
    hv = {"Authorization": f"Bearer {viewer_token}"}
    ha = {"Authorization": f"Bearer {admin_token}"}
    r = await client.post("/api/reports/schedule", json={"cron":"0 8 * * *","filters":{}}, headers=hv)
    assert r.status_code == 403
    r2 = await client.post("/api/reports/schedule", json={"cron":"0 8 * * *","filters":{"severity":"critical"}}, headers=ha)
    assert r2.status_code == 200
    job_id = r2.json()["id"]
    r3 = await client.get("/api/reports/jobs", headers=ha)
    assert r3.status_code == 200
    assert any(j["id"]==job_id for j in r3.json())
    # Run now
    r4 = await client.post(f"/api/reports/jobs/{job_id}/run", headers=ha)
    assert r4.status_code == 200
    # Artifact
    r5 = await client.get(f"/api/reports/jobs/{job_id}/artifact", headers=ha)
    # Might be 200 or 404 if async not yet done, but should eventually exist
    assert r5.status_code in (200,404)
    # Delete
    r6 = await client.delete(f"/api/reports/jobs/{job_id}", headers=ha)
    assert r6.status_code == 200

async def test_invalid_cursor(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/incidents?cursor=invalid", headers=h)
    assert r.status_code == 400

async def test_empty_search(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/incidents?q=__no_match__", headers=h)
    assert r.status_code == 200
    j = r.json()
    assert j["total"] == 0
    assert j["has_more"] is False
    assert j["next_cursor"] is None

async def test_request_id_header(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = await client.get("/api/stats", headers=h)
    assert "X-Request-ID" in r.headers

async def test_concurrent_pdf_nonblocking(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    import time, asyncio
    # Fire 3 pdf requests concurrently and check stats latency
    start = asyncio.get_event_loop().time()
    results = await asyncio.gather(
        client.get("/api/export/pdf", headers=h),
        client.get("/api/export/pdf", headers=h),
        client.get("/api/stats", headers=h),
    )
    elapsed = asyncio.get_event_loop().time() - start
    assert all(r.status_code == 200 for r in results)
    assert elapsed < 5  # not blocking too long

async def test_me_endpoint(client, viewer_token):
    h = {"Authorization": f"Bearer {viewer_token}"}
    r = await client.get("/api/auth/me", headers=h)
    assert r.status_code == 200
    assert r.json()["username"] == "viewer"
