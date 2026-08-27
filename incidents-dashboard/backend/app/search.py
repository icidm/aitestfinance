from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import Incident


def normalize_q(q: str) -> str:
    return q.strip().lower()


def q_matches(incident: Incident, q_norm: str) -> bool:
    return (
        q_norm in str(incident.id).lower()
        or q_norm in incident.title.lower()
        or q_norm in incident.service.lower()
        or q_norm in incident.description.lower()
    )


def rank_for_q(incident: Incident, q_norm: str) -> float:
    # Simple rank: count field matches weighted; keep deterministic
    score = 0.0
    if q_norm == str(incident.id).lower():
        score += 3.0
    if q_norm in incident.title.lower():
        score += 2.0
    if q_norm in incident.service.lower():
        score += 1.5
    if q_norm in incident.description.lower():
        score += 1.0
    # tie-breaker handled via id sorting
    return score


async def search_incidents_ranked(
    session: AsyncSession, q: str, status=None, severity=None, service=None, days=None
):
    # Use Python ranking for SQLite/PG parity simplified; still supports FTS abstraction
    result = await session.execute(select(Incident))
    incidents = result.scalars().all()
    # Apply filters
    if status:
        incidents = [i for i in incidents if i.status == status]
    if severity:
        incidents = [i for i in incidents if i.severity == severity]
    if service:
        incidents = [i for i in incidents if i.service == service]
    if days is not None and incidents:
        from datetime import timedelta

        latest = max(i.created_at for i in incidents)
        latest_day = latest.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = latest_day - timedelta(days=days - 1)
        end = latest_day + timedelta(days=1)
        incidents = [i for i in incidents if cutoff <= i.created_at < end]
    if not q:
        # No search, order by created_at desc
        incidents.sort(key=lambda x: (x.created_at, x.id), reverse=True)
        return [(inc, 0.0) for inc in incidents]
    q_norm = normalize_q(q)
    scored = []
    for inc in incidents:
        if q_matches(inc, q_norm):
            scored.append((inc, rank_for_q(inc, q_norm)))
    # Order by rank desc, id asc
    scored.sort(key=lambda x: (-x[1], x[0].id))
    return scored
