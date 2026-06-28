"use client";

import { createContext, useContext, useState, useCallback, useRef, ReactNode } from "react";
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

export function PipelineProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase]       = useState<Phase>("idle");
  const [statusMsg, setStatusMsg] = useState("Starting pipeline…");
  const [progress, setProgress] = useState(0);
  const [paperId, setPaperId]   = useState<number | null>(null);
  const intervalRef             = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(async (form: PipelineForm) => {
    if (intervalRef.current) clearInterval(intervalRef.current);

    setPhase("running");
    setStatusMsg("Starting pipeline…");
    setProgress(0);
    setPaperId(null);

    try {
      const initial = await runPipeline(form);
      const job_id  = initial.job_id;
      if (initial.message)  setStatusMsg(initial.message);
      if (initial.progress != null) setProgress(initial.progress);

      intervalRef.current = setInterval(async () => {
        try {
          const status = await getJobStatus(job_id);
          if (status.status === "done") {
            clearInterval(intervalRef.current!);
            setPaperId(status.paper_id ?? null);
            setPhase("done");
            setStatusMsg("Pipeline complete!");
            setProgress(100);
          } else if (status.status === "error") {
            clearInterval(intervalRef.current!);
            setPhase("error");
            setStatusMsg(status.error ?? "Unknown error");
            setProgress(0);
          } else {
            if (status.message)  setStatusMsg(status.message);
            if (status.progress != null) setProgress(status.progress);
          }
        } catch {
          clearInterval(intervalRef.current!);
          setPhase("error");
          setStatusMsg("Lost connection to server.");
        }
      }, 5000);
    } catch (err: unknown) {
      setPhase("error");
      setStatusMsg(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const reset = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
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
