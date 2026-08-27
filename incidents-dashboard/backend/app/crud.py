from datetime import datetime, timezone, timedelta
from typing import Optional, Callable
import random

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Incident, Service

SERVICES = [
    {"name": "IOP-Gateway", "description": "Inditex Open Platform API Gateway"},
    {"name": "SINT-Inventory", "description": "Sistema Integrado de Stock"},
    {"name": "RFID-Tracking", "description": "RFID item tracking service"},
    {"name": "Zara-API", "description": "Zara e-commerce backend"},
    {"name": "MassimoDutti-BFF", "description": "Massimo Dutti BFF layer"},
    {"name": "Bershka-Web", "description": "Bershka web frontend service"},
    {"name": "Oysho-Mobile", "description": "Oysho mobile API"},
    {"name": "Stradivarius-Checkout", "description": "Checkout service for Stradivarius"},
]
SEVERITIES = ["critical", "high", "medium", "low"]
SEVERITY_WEIGHTS = [0.08, 0.22, 0.40, 0.30]
STATUSES = ["open", "in_progress", "resolved"]
STATUS_WEIGHTS = [0.10, 0.15, 0.75]
INCIDENT_TEMPLATES = [
    "High latency on {service} endpoint GET /api/orders",
    "5xx errors spiking on {service} checkout flow",
    "Connection pool exhaustion in {service} database pool",
    "Memory leak detected in {service} worker process",
    "Timeout errors on {service} external payment integration",
    "Degraded read replicas for {service} PostgreSQL cluster",
    "SSL certificate expired on {service} staging environment",
    "Kubernetes pod crash loop in {service} deployment",
    "Thread pool saturation in {service} async workers",
    "Cache miss rate exceeding threshold on {service} Redis cluster",
    "Deadlock detected in {service} inventory transaction",
    "DNS resolution failure for {service} internal endpoint",
    "Unhandled exception in {service} order validation",
    "Message queue backlog growing on {service} RabbitMQ",
    "Disk space critical on {service} log aggregation node",
    "Health check failing for {service} readiness probe",
    "Rate limiter blocking legitimate traffic on {service}",
    "Data inconsistency between {service} primary and replica",
    "TLS handshake failures on {service} load balancer",
    "Graceful shutdown timeout exceeded in {service} rolling update",
    "Webhook delivery failure for {service} event stream",
    "{service} response time P99 above SLA threshold",
    "Authentication token validation errors in {service}",
    "Circuit breaker open for {service} downstream dependency",
]
DESCRIPTION_TEMPLATES = [
    "Investigation ongoing. Initial metrics show elevated error rates starting at {time}. Team has been notified.",
    "Root cause identified as a recent deployment. Rollback in progress. Impact limited to {percentage}% of traffic.",
    "Resolved after restarting the affected pods. Post-mortem scheduled. No data loss occurred.",
    "Monitoring alert triggered. Engineering team is investigating the root cause. Affected services are being isolated.",
    "Hotfix deployed to production. Monitoring shows recovery in progress. Incident will be closed after verification.",
    "Third-party dependency degraded. Vendor has been contacted. Traffic being rerouted through fallback provider.",
    "Database migration caused locking. Rolled back migration. Performance returned to baseline.",
    "Memory leak patched. New build rolling out across all regions. ETA for full recovery: {eta_minutes} minutes.",
]


def generate_data(clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
    now = clock()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    random.seed(42)
    incidents = []
    for i in range(120):
        days_ago = random.randint(0, 20)
        severity = random.choices(SEVERITIES, weights=SEVERITY_WEIGHTS, k=1)[0]
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        service = random.choice(SERVICES)
        title = random.choice(INCIDENT_TEMPLATES).format(service=service["name"])
        created_at = now - timedelta(
            days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59)
        )
        resolved_at = None
        description = random.choice(DESCRIPTION_TEMPLATES).format(
            time=created_at.strftime("%H:%M UTC"),
            percentage=random.randint(1, 30),
            eta_minutes=random.randint(15, 120),
        )
        if status == "resolved":
            resolution_hours = random.uniform(0.5, 12)
            if severity == "critical":
                resolution_hours = random.uniform(0.5, 4)
            elif severity == "high":
                resolution_hours = random.uniform(1, 6)
            resolved_at = created_at + timedelta(hours=resolution_hours)
        incidents.append(
            {
                "id": i + 1,
                "title": title,
                "service": service["name"],
                "severity": severity,
                "status": status,
                "created_at": created_at,
                "resolved_at": resolved_at,
                "description": description,
            }
        )
    services = []
    for svc in SERVICES:
        health_roll = random.random()
        if health_roll > 0.97:
            status_s = "down"
        elif health_roll > 0.85:
            status_s = "degraded"
        else:
            status_s = "healthy"
        services.append(
            {
                "name": svc["name"],
                "description": svc["description"],
                "status": status_s,
                "last_checked": now,
                "uptime_7d": round(random.uniform(98.5, 100), 2),
            }
        )
    return incidents, services


async def seed_database(
    session: AsyncSession, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
):
    incidents_data, services_data = generate_data(clock)
    # Handle case where session already has an active transaction (tests)
    if session.in_transaction():
        await session.execute(delete(Incident))
        await session.execute(delete(Service))
        for s in services_data:
            session.add(Service(**s))
        await session.flush()
        for inc in incidents_data:
            session.add(Incident(**inc))
        await session.flush()
    else:
        async with session.begin():
            await session.execute(delete(Incident))
            await session.execute(delete(Service))
            for s in services_data:
                session.add(Service(**s))
            await session.flush()
            for inc in incidents_data:
                session.add(Incident(**inc))


async def reset_database(
    session: AsyncSession, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
):
    await seed_database(session, clock)


async def list_incidents_filtered(
    session: AsyncSession,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    service: Optional[str] = None,
    q: Optional[str] = None,
    days: Optional[int] = None,
):
    # Helper for export/pptx/pdf filtering (not paginated)
    result = await session.execute(
        select(Incident).order_by(Incident.created_at.desc(), Incident.id.desc())
    )
    incidents = result.scalars().all()
    # Apply filters in Python to keep parity across dialects simply; optimized queries use SQL where needed for pagination
    filtered = incidents
    if status:
        filtered = [i for i in filtered if i.status == status]
    if severity:
        filtered = [i for i in filtered if i.severity == severity]
    if service:
        filtered = [i for i in filtered if i.service == service]
    if q:
        q_norm = q.strip().lower()
        filtered = [
            i
            for i in filtered
            if q_norm in str(i.id).lower()
            or q_norm in i.title.lower()
            or q_norm in i.service.lower()
            or q_norm in i.description.lower()
        ]
    if days is not None and filtered:
        # latest-day window semantics
        latest = max(i.created_at for i in filtered)
        latest_day = latest.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = latest_day - timedelta(days=days - 1)
        end_exclusive = latest_day + timedelta(days=1)
        filtered = [i for i in filtered if cutoff <= i.created_at < end_exclusive]
    return filtered


def compute_stats(incidents):
    total = len(incidents)
    open_count = sum(1 for i in incidents if i.status in ("open", "in_progress"))
    resolved_count = sum(1 for i in incidents if i.status == "resolved")
    critical_open = sum(
        1 for i in incidents if i.severity == "critical" and i.status in ("open", "in_progress")
    )
    resolved_times = []
    for i in incidents:
        if i.status == "resolved" and i.resolved_at and i.created_at:
            diff = (i.resolved_at - i.created_at).total_seconds() / 60
            if diff > 0:
                resolved_times.append(diff)
    mttr = round(sum(resolved_times) / len(resolved_times), 1) if resolved_times else None
    by_severity = {
        sev: sum(1 for i in incidents if i.severity == sev)
        for sev in ("critical", "high", "medium", "low")
    }
    by_status = {
        st: sum(1 for i in incidents if i.status == st)
        for st in ("open", "in_progress", "resolved")
    }
    return {
        "total_incidents": total,
        "open_incidents": open_count,
        "resolved_incidents": resolved_count,
        "critical_open": critical_open,
        "mttr_minutes": mttr,
        "by_severity": by_severity,
        "by_status": by_status,
    }


def compute_timeline(incidents, days: int = 14, now: Optional[datetime] = None):
    if now is None:
        now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(days=days)

    def _aware(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    cutoff = _aware(cutoff)
    filtered = [i for i in incidents if _aware(i.created_at) >= cutoff]
    buckets = {}
    for i in filtered:
        day = i.created_at.strftime("%Y-%m-%d")
        if day not in buckets:
            buckets[day] = {
                "date": day,
                "total": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "resolved": 0,
            }
        buckets[day]["total"] += 1
        buckets[day][i.severity] += 1
        if i.status == "resolved":
            buckets[day]["resolved"] += 1
    return sorted(buckets.values(), key=lambda x: x["date"])
