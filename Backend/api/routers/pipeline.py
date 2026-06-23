import threading
import uuid

from fastapi import APIRouter, HTTPException

from api.schemas import JobStatus, RunPipelineIn

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _run_job(job_id: str, body: RunPipelineIn) -> None:
    def update_progress(message: str, progress: int) -> None:
        with _lock:
            if _jobs.get(job_id, {}).get("status") == "running":
                _jobs[job_id]["message"]  = message
                _jobs[job_id]["progress"] = progress

    try:
        from graph.orchestrator import run_pipeline_with_params
        paper_id = run_pipeline_with_params(
            body.qp_url,
            body.qp_metadata_raw,
            body.ms_url,
            body.ms_metadata_raw,
            progress_cb=update_progress,
        )
        with _lock:
            _jobs[job_id] = {"status": "done", "paper_id": paper_id, "message": "Done!", "progress": 100}
    except Exception as exc:
        with _lock:
            _jobs[job_id] = {"status": "error", "error": str(exc), "message": str(exc), "progress": 0}


@router.post("/run", response_model=JobStatus)
def run_pipeline(body: RunPipelineIn) -> JobStatus:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {"status": "running", "message": "Starting pipeline…", "progress": 0}
    thread = threading.Thread(target=_run_job, args=(job_id, body), daemon=True)
    thread.start()
    return JobStatus(job_id=job_id, status="running", message="Starting pipeline…", progress=0)


@router.get("/status/{job_id}", response_model=JobStatus)
def get_status(job_id: str) -> JobStatus:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(job_id=job_id, **job)
