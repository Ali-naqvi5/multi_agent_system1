"use client";

import { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from "react";
import { runPipeline, getJobStatus, deleteJob, ApiError } from "@/lib/api";

type Phase = "idle" | "running" | "done" | "error";

interface PipelineForm {
  qp_url: string;
  qp_metadata_raw: string;
  ms_url: string;
  ms_metadata_raw: string;
}

interface PipelineCtx {
  phase: Phase;
  statusMsg: string;
  progress: number;
  paperId: number | null;
  start: (form: PipelineForm) => Promise<void>;
  reset: () => void;
}

const Ctx = createContext<PipelineCtx | null>(null);

// Stored in localStorage (not sessionStorage) so a running job is recoverable
// across full refreshes and new tabs. The DB-backed status endpoint is the
// source of truth, so a stale id simply 404s and we fall back to idle.
const LS_KEY = "exameval_job_id";

export function PipelineProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase]         = useState<Phase>("idle");
  const [statusMsg, setStatusMsg] = useState("Starting pipeline…");
  const [progress, setProgress]   = useState(0);
  const [paperId, setPaperId]     = useState<number | null>(null);
  const intervalRef               = useRef<ReturnType<typeof setInterval> | null>(null);

  function clearTimer() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }

  function poll(job_id: string) {
    clearTimer();
    intervalRef.current = setInterval(async () => {
      try {
        const s = await getJobStatus(job_id);
        if (s.status === "done") {
          clearTimer();
          localStorage.removeItem(LS_KEY);
          deleteJob(job_id);   // run finished — clear the now-irrelevant job row
          setPaperId(s.paper_id ?? null);
          setPhase("done");
          setStatusMsg("Pipeline complete!");
          setProgress(100);
        } else if (s.status === "error") {
          clearTimer();
          localStorage.removeItem(LS_KEY);
          deleteJob(job_id);   // run ended in error — clear the job row
          setPhase("error");
          setStatusMsg(s.error ?? "Unknown error");
          setProgress(0);
        } else {
          if (s.message)        setStatusMsg(s.message);
          if (s.progress != null) setProgress(s.progress);
        }
      } catch (err) {
        clearTimer();
        localStorage.removeItem(LS_KEY);
        if (err instanceof ApiError && err.status === 404) {
          // Job no longer exists on the server — return to a clean idle state.
          setPhase("idle");
          setProgress(0);
        } else {
          setPhase("error");
          setStatusMsg("Lost connection to server.");
        }
      }
    }, 5000);
  }

  // On every mount (initial load or navigation back): resume a saved job
  useEffect(() => {
    const savedId = localStorage.getItem(LS_KEY);
    if (!savedId) return;

    setPhase("running");
    setStatusMsg("Reconnecting to pipeline…");

    getJobStatus(savedId)
      .then((s) => {
        if (s.status === "done") {
          localStorage.removeItem(LS_KEY);
          deleteJob(savedId);   // run finished — clear the now-irrelevant job row
          setPaperId(s.paper_id ?? null);
          setPhase("done");
          setStatusMsg("Pipeline complete!");
          setProgress(100);
        } else if (s.status === "error") {
          localStorage.removeItem(LS_KEY);
          deleteJob(savedId);   // run ended in error — clear the job row
          setPhase("error");
          setStatusMsg(s.error ?? "Unknown error");
          setProgress(0);
        } else {
          if (s.message)        setStatusMsg(s.message);
          if (s.progress != null) setProgress(s.progress);
          poll(savedId);
        }
      })
      .catch((err) => {
        localStorage.removeItem(LS_KEY);
        if (err instanceof ApiError && err.status === 404) {
          // Saved id points to a job that no longer exists — start fresh.
          setPhase("idle");
          setProgress(0);
        } else {
          setPhase("error");
          setStatusMsg("Lost connection to server.");
        }
      });

    return clearTimer;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const start = useCallback(async (form: PipelineForm) => {
    clearTimer();
    setPhase("running");
    setStatusMsg("Starting pipeline…");
    setProgress(0);
    setPaperId(null);

    try {
      const initial = await runPipeline(form);
      const job_id  = initial.job_id;
      localStorage.setItem(LS_KEY, job_id);
      if (initial.message)        setStatusMsg(initial.message);
      if (initial.progress != null) setProgress(initial.progress);
      poll(job_id);
    } catch (err: unknown) {
      setPhase("error");
      setStatusMsg(err instanceof Error ? err.message : String(err));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = useCallback(() => {
    clearTimer();
    localStorage.removeItem(LS_KEY);
    setPhase("idle");
    setStatusMsg("Starting pipeline…");
    setProgress(0);
    setPaperId(null);
  }, []);

  return (
    <Ctx.Provider value={{ phase, statusMsg, progress, paperId, start, reset }}>
      {children}
    </Ctx.Provider>
  );
}

export function usePipeline(): PipelineCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePipeline must be used inside PipelineProvider");
  return ctx;
}
