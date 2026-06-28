"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getPaper } from "@/lib/api";
import type { PaperDetailOut } from "@/lib/api";
import { QuestionCard } from "@/components/QuestionCard";

export default function PaperPage() {
  const params = useParams();
  const id = Number(params.id);

  const [paper, setPaper]     = useState<PaperDetailOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);

  useEffect(() => {
    if (!id) return;
    getPaper(id)
      .then(setPaper)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400 text-sm gap-2">
        <span className="w-4 h-4 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
        Loading paper…
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-red-700 text-sm">
        Paper not found or API server is unreachable.{" "}
        <Link href="/papers" className="underline font-medium">Back to papers</Link>
      </div>
    );
  }

  const title     = [paper.level, paper.subject].filter(Boolean).join(" · ") || "Paper";
  const meta      = [paper.board, paper.year, paper.paper_code ? `Paper ${paper.paper_code}` : null, paper.tier]
    .filter(Boolean).join(" · ");
  const validated = paper.questions.filter(q => q.verification_status === "validated").length;
  const total     = paper.questions.length;
  const pct       = total > 0 ? Math.round((validated / total) * 100) : 0;

  return (
    <div>
      {/* Back nav */}
      <Link href="/papers" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-blue-600 mb-6 transition-colors">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
        </svg>
        All Papers
      </Link>

      {/* Paper header card */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 mb-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{title}</h1>
            {meta && <p className="text-slate-500 text-sm mt-1">{meta}</p>}
          </div>

          <div className="flex items-center gap-4 flex-shrink-0">
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-800">{total}</p>
              <p className="text-xs text-slate-400 mt-0.5">Questions</p>
            </div>
            <div className="w-px h-10 bg-slate-200" />
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600">{validated}</p>
              <p className="text-xs text-slate-400 mt-0.5">Validated</p>
            </div>
            <div className="w-px h-10 bg-slate-200" />
            <div className="text-center">
              <p className="text-2xl font-bold text-blue-600">{pct}%</p>
              <p className="text-xs text-slate-400 mt-0.5">Pass rate</p>
            </div>
          </div>
        </div>

        {total > 0 && (
          <div className="mt-5">
            <div className="flex justify-between text-xs text-slate-400 mb-1.5">
              <span>Validation coverage</span>
              <span>{validated}/{total} questions</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
              <div className="h-2 bg-emerald-500 rounded-full" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
      </div>

      {/* Questions */}
      <div className="space-y-4">
        {paper.questions.map((q) => (
          <QuestionCard key={q.id} q={q} />
        ))}
      </div>
    </div>
  );
}
