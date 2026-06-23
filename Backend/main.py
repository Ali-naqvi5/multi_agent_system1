import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

from db.models import Base
from graph.orchestrator import run_pipeline

load_dotenv()


async def _ensure_tables() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("  DATABASE_URL not set — skipping table setup.")
        return
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


def main():
    print("\n" + "="*60)
    print("  PAST PAPER EXTRACTION SYSTEM")
    print("="*60 + "\n")

    asyncio.run(_ensure_tables())
    run_pipeline()


if __name__ == "__main__":
    main()
