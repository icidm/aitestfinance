import asyncio
import json
from typing import List
from datetime import datetime, timezone


class EventBus:
    def __init__(self):
        self.subscribers: List[asyncio.Queue] = []
        self.seq = 0
        self.buffer: List[dict] = []
        self.max_buffer = 200

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)

    async def publish(self, event: dict):
        self.seq += 1
        event["seq"] = self.seq
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.buffer.append(event)
        if len(self.buffer) > self.max_buffer:
            self.buffer.pop(0)
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def since(self, last_event_id: str):
        try:
            last = int(last_event_id)
        except Exception:
            return list(self.buffer)
        return [e for e in self.buffer if e.get("seq", 0) > last]


bus = EventBus()


def sse_format(event: dict) -> str:
    seq = event.get("seq", 0)
    data = json.dumps(event)
    return f"id: {seq}\ndata: {data}\n\n"


def matches_filters(event: dict, query_params) -> bool:
    # event types: incident.create, incident.resolve, stats
    # Filter by status/severity/service/q if present
    inc = event.get("incident")
    if not inc:
        return True
    status = query_params.get("status")
    severity = query_params.get("severity")
    service = query_params.get("service")
    q = query_params.get("q")
    if status and inc.get("status") != status:
        return False
    if severity and inc.get("severity") != severity:
        return False
    if service and inc.get("service") != service:
        return False
    if q:
        qn = q.strip().lower()
        if (
            qn not in str(inc.get("id", "")).lower()
            and qn not in inc.get("title", "").lower()
            and qn not in inc.get("service", "").lower()
            and qn not in inc.get("description", "").lower()
        ):
            return False
    return True
