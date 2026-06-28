import os
import re
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

_engine = None
_Session = None


def _prepare_url(url: str) -> tuple[str, dict]:
    # asyncpg rejects sslmode= in the URL — strip it and pass ssl via connect_args
    clean = re.sub(r"[?&]sslmode=[^&]*", "", url).rstrip("?&")
    is_remote = "localhost" not in clean and "127.0.0.1" not in clean
    connect_args = {"ssl": "require"} if is_remote else {}
    return clean, connect_args


def _session_factory():
    global _engine, _Session
    if _Session is None:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set")
        clean_url, connect_args = _prepare_url(db_url)
        _engine = create_async_engine(clean_url, connect_args=connect_args)
        _Session = async_sessionmaker(_engine, expire_on_commit=False)
    return _Session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    Session = _session_factory()
    async with Session() as session:
        yield session
