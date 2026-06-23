import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.routers import images, papers, pipeline  # noqa: E402


async def _ensure_tables() -> None:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("  [startup] DATABASE_URL not set — skipping table creation.")
        return
    from sqlalchemy.ext.asyncio import create_async_engine
    from db.models import Base
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("  [startup] DB tables ready.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _ensure_tables()
    yield


app = FastAPI(title="Past Paper API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router, prefix="/api")
app.include_router(papers.router,   prefix="/api")
app.include_router(images.router,   prefix="/api")


@app.get("/")
def health() -> dict:
    return {"status": "ok"}
