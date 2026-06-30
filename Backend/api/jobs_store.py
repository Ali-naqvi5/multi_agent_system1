"""Durable pipeline-run status, backed by the database.

The pipeline runs in a synchronous background thread, so job-status writes use a
synchronous SQLAlchemy engine (psycopg2) here — separate from the async engine in
deps.py used for papers/images. Persisting status to the DB means it survives
backend restarts/redeploys and is correct regardless of which worker serves a
status poll. Each run is one row keyed by its UUID job_id, so users never mix.
"""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, update, delete
from sqlalchemy.orm import sessionmaker

from db.models import Job

_engine = None
_Session = None


def _sync_url(url: str) -> str:
    """Convert the configured DATABASE_URL to a synchronous psycopg2 URL.

    psycopg2 accepts `sslmode=` in the URL (unlike asyncpg), so we only swap the
    driver and leave any query string intact.
    """
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "+psycopg2")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def _session_factory():
    global _engine, _Session
    if _Session is None:
        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(_sync_url(db_url), pool_pre_ping=True)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _Session


def create_job(job_id: str, message: str = "Starting pipeline…") -> None:
    Session = _session_factory()
    with Session() as s:
        s.add(Job(id=job_id, status="running", message=message, progress=0))
        s.commit()


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    message: str | None = None,
    progress: int | None = None,
    paper_id: int | None = None,
    error: str | None = None,
) -> None:
    fields: dict = {}
    if status is not None:
        fields["status"] = status
    if message is not None:
        fields["message"] = message
    if progress is not None:
        fields["progress"] = progress
    if paper_id is not None:
        fields["paper_id"] = paper_id
    if error is not None:
        fields["error"] = error
    if not fields:
        return
    Session = _session_factory()
    with Session() as s:
        s.execute(update(Job).where(Job.id == job_id).values(**fields))
        s.commit()


def get_job(job_id: str) -> dict | None:
    """Return the job as a dict matching the JobStatus schema, or None if absent."""
    Session = _session_factory()
    with Session() as s:
        job = s.get(Job, job_id)
        if job is None:
            return None
        return {
            "status":   job.status,
            "message":  job.message,
            "progress": job.progress,
            "paper_id": job.paper_id,
            "error":    job.error,
        }


def delete_job(job_id: str) -> None:
    """Remove a single job row. Never affects the papers table (no FK link)."""
    Session = _session_factory()
    with Session() as s:
        s.execute(delete(Job).where(Job.id == job_id))
        s.commit()


def purge_stale_jobs(max_age_hours: int = 6) -> None:
    """Safety net: drop job rows untouched for a while (e.g. runs abandoned before
    completion), so the table can't grow unbounded. Papers are never touched."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    Session = _session_factory()
    with Session() as s:
        s.execute(delete(Job).where(Job.updated_at < cutoff))
        s.commit()
