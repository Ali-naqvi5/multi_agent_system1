"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { usePipeline } from "@/lib/pipeline-context";

type Field = { label: string; key: keyof FormState; placeholder: string };

interface FormState {
  qp_url: string;
  qp_metadata_raw: string;
  ms_url: string;
  ms_metadata_raw: string;
}

const FIELDS: Field[] = [
  { label: "Question Paper URL",  key: "qp_url",          placeholder: "https://…/question-paper.pdf" },
  { label: "QP Metadata",         key: "qp_metadata_raw", placeholder: "e.g. Edexcel GCSE Mathematics 2023 Paper 1H" },
  { label: "Mark Scheme URL",     key: "ms_url",           placeholder: "https://…/mark-scheme.pdf" },
  { label: "MS Metadata",         key: "ms_metadata_raw",  placeholder: "e.g. Edexcel GCSE Mathematics 2023 Paper 1H Mark Scheme" },
];

export default function HomePage() {
  const router = useRouter();
  const { phase, statusMsg, progress, paperId, start, reset } = usePipeline();
  const [form, setForm] = useState<FormState>({
    qp_url: "", qp_metadata_raw: "", ms_url: "", ms_metadata_raw: "",
  });

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault();
    await start(form);
  }

  return (
    <div className="max-w-2xl mx-auto">

      {/* Page header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Run Pipeline</h1>
        <p className="mt-2 text-slate-500 text-sm leading-relaxed">
          Paste the PDF links and metadata for a past paper and its mark scheme.
          The pipeline extracts questions, generates AI student answers, grades them,
          and stores everything in the database.
        </p>
      </div>

      {/* Form */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">Paper Details</h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          <div className="grid grid-cols-1 gap-5">
            {FIELDS.map(({ label, key, placeholder }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">{label}</label>
                <input
                  type="text"
                  required
                  value={form[key]}
                  placeholder={placeholder}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  disabled={phase === "running"}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-slate-50 disabled:text-slate-400 transition-shadow"
                />
              </div>
            ))}
          </div>

          <button
            type="submit"
            disabled={phase === "running"}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-semibold rounded-xl py-3 text-sm transition-colors shadow-sm mt-2"
          >
            {phase === "running" ? "Pipeline running…" : "Run Pipeline"}
          </button>
        </form>
      </div>

      {/* Status panel */}
      {phase !== "idle" && (
        <div className={`mt-5 rounded-2xl border p-5 ${
          phase === "error" ? "bg-red-50 border-red-200"
          : phase === "done" ? "bg-emerald-50 border-emerald-200"
          : "bg-blue-50 border-blue-200"
        }`}>

          {/* Status line */}
          <div className="flex items-center gap-3 mb-4">
            {phase === "running" && (
              <span className="inline-block w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
            )}
            {phase === "done" && (
              <span className="inline-flex items-center justify-center w-5 h-5 bg-emerald-500 rounded-full flex-shrink-0">
                <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </span>
            )}
            {phase === "error" && (
              <span className="inline-flex items-center justify-center w-5 h-5 bg-red-500 rounded-full flex-shrink-0 text-white text-xs font-bold">✕</span>
            )}
            <span className={`text-sm font-semibold ${
              phase === "error" ? "text-red-700"
              : phase === "done" ? "text-emerald-700"
              : "text-blue-700"
            }`}>
              {statusMsg}
            </span>
          </div>

          {/* Progress bar */}
          {(phase === "running" || phase === "done") && (
            <>
              <div className="w-full bg-white/60 rounded-full h-2.5 overflow-hidden border border-white/80">
                <div
                  className={`h-2.5 rounded-full transition-all duration-700 ease-out ${
                    phase === "done" ? "bg-emerald-500" : "bg-blue-500"
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="flex justify-between mt-1.5 text-xs text-blue-500">
                <span className="text-slate-400">Progress</span>
                <span className="font-semibold">{progress}%</span>
              </div>
            </>
          )}

          {/* Warning */}
          {phase === "running" && (
            <p className="mt-3 text-xs text-blue-600 bg-blue-100 rounded-lg px-3 py-2 text-center">
              ⚠ Do not close or refresh this page while the pipeline is running.
            </p>
          )}

          {/* CTAs */}
          {phase === "done" && paperId && (
            <button
              onClick={() => router.push(`/papers/${paperId}`)}
              className="mt-4 w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl py-2.5 text-sm transition-colors shadow-sm"
            >
              View Results →
            </button>
          )}
          {(phase === "done" || phase === "error") && (
            <button
              onClick={reset}
              className="mt-2 w-full text-sm text-slate-500 hover:text-slate-700 underline"
            >
              Run another pipeline
            </button>
          )}
        </div>
      )}
    </div>
  );
}
