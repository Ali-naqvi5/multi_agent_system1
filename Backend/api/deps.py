import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

_engine = None
_Session = None


def _session_factory():
    global _engine, _Session
    if _Session is None:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_async_engine(db_url)
        _Session = async_sessionmaker(_engine, expire_on_commit=False)
    return _Session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    Session = _session_factory()
    async with Session() as session:
        yield session
