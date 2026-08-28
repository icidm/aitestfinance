import base64
import json
from datetime import datetime
from fastapi import HTTPException

MAX_OFFSET = 10000


def encode_cursor(created_at: datetime, id: int) -> str:
    payload = {"v": 1, "created_at": created_at.isoformat(), "id": id}
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str):
    try:
        pad = "=" * (-len(cursor) % 4)
        data = base64.urlsafe_b64decode(cursor + pad)
        obj = json.loads(data.decode())
        if obj.get("v") != 1:
            raise ValueError("invalid version")
        created_at = datetime.fromisoformat(obj["created_at"])
        id_val = int(obj["id"])
        return created_at, id_val
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


def encode_fts_cursor(rank: float, id: int) -> str:
    payload = {"v": 1, "rank": rank, "id": id}
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_fts_cursor(cursor: str):
    try:
        pad = "=" * (-len(cursor) % 4)
        data = base64.urlsafe_b64decode(cursor + pad)
        obj = json.loads(data.decode())
        if obj.get("v") != 1:
            raise ValueError("invalid version")
        rank = float(obj["rank"])
        id_val = int(obj["id"])
        return rank, id_val
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")
