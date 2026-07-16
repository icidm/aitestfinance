import json
import os
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

app = FastAPI(
    title="Inditex Incidents Dashboard API",
    version="1.0.0",
    description="PoC API for production incident monitoring",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_data():
    with open(DATA_FILE) as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class CreateIncidentRequest(BaseModel):
    title: str
    service: str
    severity: str
    description: str = ""


@app.get("/api/stats")
def get_stats():
    data = load_data()
    incidents = data["incidents"]
    total = len(incidents)
    open_count = sum(1 for i in incidents if i["status"] in ("open", "in_progress"))
    resolved_count = sum(1 for i in incidents if i["status"] == "resolved")
    critical_open = sum(
        1 for i in incidents if i["severity"] == "critical" and i["status"] in ("open", "in_progress")
    )

    mttr_minutes = None
    resolved_times = []
    for i in incidents:
        if i["status"] == "resolved" and i["resolved_at"] and i["created_at"]:
            created = datetime.fromisoformat(i["created_at"])
            resolved = datetime.fromisoformat(i["resolved_at"])
            diff_min = (resolved - created).total_seconds() / 60
            if diff_min > 0:
                resolved_times.append(diff_min)
    if resolved_times:
        mttr_minutes = round(sum(resolved_times) / len(resolved_times), 1)

    return {
        "total_incidents": total,
        "open_incidents": open_count,
        "resolved_incidents": resolved_count,
        "critical_open": critical_open,
        "mttr_minutes": mttr_minutes,
        "by_severity": {
            sev: sum(1 for i in incidents if i["severity"] == sev)
            for sev in ("critical", "high", "medium", "low")
        },
        "by_status": {
            st: sum(1 for i in incidents if i["status"] == st)
            for st in ("open", "in_progress", "resolved")
        },
    }


@app.get("/api/incidents")
def get_incidents(
    status: str = Query(None),
    severity: str = Query(None),
    service: str = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    data = load_data()
    incidents = data["incidents"]

    if status:
        incidents = [i for i in incidents if i["status"] == status]
    if severity:
        incidents = [i for i in incidents if i["severity"] == severity]
    if service:
        incidents = [i for i in incidents if i["service"] == service]

    incidents.sort(key=lambda x: x["created_at"], reverse=True)
    total = len(incidents)
    page = incidents[offset : offset + limit]

    return {"total": total, "offset": offset, "limit": limit, "incidents": page}


@app.get("/api/incidents/timeline")
def get_incidents_timeline(days: int = Query(14)):
    data = load_data()
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(days=days)
    incidents = [
        i
        for i in data["incidents"]
        if datetime.fromisoformat(i["created_at"]) >= cutoff
    ]

    day_buckets = {}
    for i in incidents:
        day = datetime.fromisoformat(i["created_at"]).strftime("%Y-%m-%d")
        if day not in day_buckets:
            day_buckets[day] = {"date": day, "total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "resolved": 0}
        day_buckets[day]["total"] += 1
        day_buckets[day][i["severity"]] += 1
        if i["status"] == "resolved":
            day_buckets[day]["resolved"] += 1

    return sorted(day_buckets.values(), key=lambda x: x["date"])


@app.get("/api/services")
def get_services():
    data = load_data()
    services = data["services"]

    for svc in services:
        svc_incidents = [i for i in data["incidents"] if i["service"] == svc["name"] and i["status"] in ("open", "in_progress")]
        svc["active_incidents"] = len(svc_incidents)

    return services


@app.put("/api/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int):
    data = load_data()
    for i in data["incidents"]:
        if i["id"] == incident_id:
            i["status"] = "resolved"
            i["resolved_at"] = datetime.now().isoformat()
            save_data(data)
            return {"ok": True, "incident": i}
    return {"ok": False, "error": "Incident not found"}, 404


@app.post("/api/incidents")
def create_incident(req: CreateIncidentRequest):
    data = load_data()
    max_id = max((i["id"] for i in data["incidents"]), default=0)
    incident = {
        "id": max_id + 1,
        "title": req.title,
        "service": req.service,
        "severity": req.severity,
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "resolved_at": None,
        "description": req.description,
    }
    data["incidents"].append(incident)
    save_data(data)
    return incident


@app.post("/api/reset")
def reset_data():
    from seed import main as seed_main
    seed_main()
    return {"ok": True, "message": "Data reset to seed state"}


FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
app.mount("/dashboard", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
