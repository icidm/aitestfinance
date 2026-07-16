import json
import random
from datetime import datetime, timedelta

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

NOW = datetime.now()

def generate_incidents():
    incidents = []
    incident_id = 1

    for i in range(120):
        days_ago = random.randint(0, 20)
        severity = random.choices(SEVERITIES, weights=SEVERITY_WEIGHTS, k=1)[0]
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

        service = random.choice(SERVICES)
        title = random.choice(INCIDENT_TEMPLATES).format(service=service["name"])

        created_at = NOW - timedelta(
            days=days_ago,
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
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

        incidents.append({
            "id": incident_id,
            "title": title,
            "service": service["name"],
            "severity": severity,
            "status": status,
            "created_at": created_at.isoformat(),
            "resolved_at": resolved_at.isoformat() if resolved_at else None,
            "description": description,
        })
        incident_id += 1

    return incidents


def generate_services():
    services = []
    for svc in SERVICES:
        health_roll = random.random()
        if health_roll > 0.85:
            status = "degraded"
        elif health_roll > 0.97:
            status = "down"
        else:
            status = "healthy"

        services.append({
            "name": svc["name"],
            "description": svc["description"],
            "status": status,
            "last_checked": NOW.isoformat(),
            "uptime_7d": round(random.uniform(98.5, 100), 2),
        })
    return services


def main():
    random.seed(42)

    data = {
        "generated_at": NOW.isoformat(),
        "incidents": generate_incidents(),
        "services": generate_services(),
    }

    with open("data.json", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(data['incidents'])} incidents across {len(data['services'])} services")
    print("Data written to data.json")


if __name__ == "__main__":
    main()
