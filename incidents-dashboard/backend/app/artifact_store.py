import os
from datetime import datetime

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts")


def ensure_dir(job_id: str):
    path = os.path.join(BASE_DIR, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def save_artifact(job_id: str, data: bytes) -> str:
    dir_path = ensure_dir(job_id)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ts}.pdf"
    full = os.path.join(dir_path, fname)
    with open(full, "wb") as f:
        f.write(data)
    return full


def get_artifact_path(job_id: str, filename: str | None = None):
    # Return latest if no filename
    dir_path = os.path.join(BASE_DIR, job_id)
    if not os.path.exists(dir_path):
        return None
    if filename:
        p = os.path.join(dir_path, filename)
        return p if os.path.exists(p) else None
    files = sorted(os.listdir(dir_path))
    if not files:
        return None
    return os.path.join(dir_path, files[-1])
