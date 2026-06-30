import threading
import uuid

from fastapi import APIRouter, HTTPException

from api.schemas import JobStatus, RunPipelineIn
from api.jobs_store import create_job, update_job, get_job, delete_job, purge_stale_jobs

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _run_job(job_id: str, body: RunPipelineIn) -> None:
    # Dedupe DB writes: only persist when the progress line actually changes.
    last: dict = {"message": None, "progress": None}

    def update_progress(message: str, progress: int) -> None:
        if message == last["message"] and progress == last["progress"]:
            return
        last["message"] = message
        last["progress"] = progress
        update_job(job_id, status="running", message=message, progress=progress)

    try:
        from graph.orchestrator import run_pipeline_with_params
        paper_id = run_pipeline_with_params(
            body.qp_url,
            body.qp_metadata_raw,
            body.ms_url,
            body.ms_metadata_raw,
            progress_cb=update_progress,
        )
        update_job(job_id, status="done", message="Done!", progress=100, paper_id=paper_id)
    except Exception as exc:
        update_job(job_id, status="error", message=str(exc), progress=0, error=str(exc))


@router.post("/run", response_model=JobStatus)
def run_pipeline(body: RunPipelineIn) -> JobStatus:
    purge_stale_jobs()  # safety net: clear rows from runs abandoned long ago
    job_id = str(uuid.uuid4())
    create_job(job_id, message="Starting pipeline…")
    thread = threading.Thread(target=_run_job, args=(job_id, body), daemon=True)
    thread.start()
    return JobStatus(job_id=job_id, status="running", message="Starting pipeline…", progress=0)


@router.get("/status/{job_id}", response_model=JobStatus)
def get_status(job_id: str) -> JobStatus:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(job_id=job_id, **job)


@router.delete("/status/{job_id}")
def delete_status(job_id: str) -> dict:
    """Called by the client once it has read a terminal (done/error) status, so the
    now-irrelevant job row is cleared. Does not affect the saved paper."""
    delete_job(job_id)
    return {"deleted": True}
