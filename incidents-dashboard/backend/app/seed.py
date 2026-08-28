from datetime import datetime, timezone
from typing import Callable
from .crud import seed_database as crud_seed

# Thin shim to keep backward compat with seed.main()
import asyncio


async def _seed_with_clock(clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
    from .db import async_session_factory

    async with async_session_factory() as session:
        await crud_seed(session, clock)


def main(clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
    asyncio.run(_seed_with_clock(clock))
