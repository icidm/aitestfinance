from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        url = settings.DATABASE_URL_SYNC
        # Use memory store for sqlite test db to avoid locking
        if "test.db" in url or ":memory:" in url:
            from apscheduler.jobstores.memory import MemoryJobStore

            jobstores = {"default": MemoryJobStore()}
        else:
            jobstores = {"default": SQLAlchemyJobStore(url=url)}
        _scheduler = BackgroundScheduler(
            jobstores=jobstores,
            job_defaults={"coalesce": True, "misfire_grace_time": 300, "max_instances": 1},
        )
    return _scheduler


def start_scheduler():
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        # Reload jobs from DB? SQLAlchemyJobStore already loads.
    return sched


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


def add_scheduled_job(job_id: str, cron: str | None, interval_seconds: int | None, func, args=None):
    sched = get_scheduler()
    if cron:
        try:
            trigger = CronTrigger.from_crontab(cron)
        except Exception as e:
            raise ValueError(f"Invalid cron: {e}")
    elif interval_seconds:
        trigger = IntervalTrigger(seconds=interval_seconds)
    else:
        raise ValueError("cron or interval required")
    # remove existing
    try:
        sched.remove_job(job_id)
    except Exception:
        pass
    sched.add_job(
        func,
        trigger=trigger,
        id=job_id,
        args=args or [],
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=300,
        max_instances=1,
    )
    return sched.get_job(job_id)


def remove_job(job_id: str):
    sched = get_scheduler()
    try:
        sched.remove_job(job_id)
    except Exception:
        pass
