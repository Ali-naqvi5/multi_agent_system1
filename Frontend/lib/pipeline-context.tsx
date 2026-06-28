"use client";

import { createContext, useContext, useState, useCallback, useRef, useEffect, ReactNode } from "react";
import { runPipeline, getJobStatus } from "@/lib/api";

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

const SS_KEY = "exameval_job_id";

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
          sessionStorage.removeItem(SS_KEY);
          setPaperId(s.paper_id ?? null);
          setPhase("done");
          setStatusMsg("Pipeline complete!");
          setProgress(100);
        } else if (s.status === "error") {
          clearTimer();
          sessionStorage.removeItem(SS_KEY);
          setPhase("error");
          setStatusMsg(s.error ?? "Unknown error");
          setProgress(0);
        } else {
          if (s.message)        setStatusMsg(s.message);
          if (s.progress != null) setProgress(s.progress);
        }
      } catch {
        clearTimer();
        sessionStorage.removeItem(SS_KEY);
        setPhase("error");
        setStatusMsg("Lost connection to server.");
      }
    }, 5000);
  }

  // On every mount (initial load or navigation back): resume a saved job
  useEffect(() => {
    const savedId = sessionStorage.getItem(SS_KEY);
    if (!savedId) return;

    setPhase("running");
    setStatusMsg("Reconnecting to pipeline…");

    getJobStatus(savedId)
      .then((s) => {
        if (s.status === "done") {
          sessionStorage.removeItem(SS_KEY);
          setPaperId(s.paper_id ?? null);
          setPhase("done");
          setStatusMsg("Pipeline complete!");
          setProgress(100);
        } else if (s.status === "error") {
          sessionStorage.removeItem(SS_KEY);
          setPhase("error");
          setStatusMsg(s.error ?? "Unknown error");
          setProgress(0);
        } else {
          if (s.message)        setStatusMsg(s.message);
          if (s.progress != null) setProgress(s.progress);
          poll(savedId);
        }
      })
      .catch(() => {
        sessionStorage.removeItem(SS_KEY);
        setPhase("error");
        setStatusMsg("Lost connection to server.");
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
      sessionStorage.setItem(SS_KEY, job_id);
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
    sessionStorage.removeItem(SS_KEY);
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
