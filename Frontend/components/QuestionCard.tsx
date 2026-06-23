"use client";

import { useState } from "react";
import type { QuestionOut } from "@/lib/api";
import { imageUrl } from "@/lib/api";
import { MathText } from "@/components/MathText";

const VERDICT_STYLE: Record<string, string> = {
  pass: "bg-emerald-100 text-emerald-700 border-emerald-200",
  fail: "bg-red-100 text-red-600 border-red-200",
};

const STATUS_STYLE: Record<string, { badge: string; dot: string }> = {
  validated:      { badge: "bg-emerald-50 text-emerald-700 border-emerald-200", dot: "bg-emerald-500" },
  unconvergeable: { badge: "bg-amber-50 text-amber-700 border-amber-200",   dot: "bg-amber-400" },
  skipped:        { badge: "bg-slate-100 text-slate-500 border-slate-200",   dot: "bg-slate-400" },
};

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-4 h-4 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

export function QuestionCard({ q }: { q: QuestionOut }) {
  const [showMs, setShowMs]          = useState(false);
  const [showAnswers, setShowAnswers] = useState(false);

  const statusStyle = q.verification_status ? STATUS_STYLE[q.verification_status] : null;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">

      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-slate-100 bg-slate-50/70">
        <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-blue-600 text-white text-xs font-bold flex-shrink-0">
          {q.question_number}
        </span>
        {q.marks != null && (
          <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full font-medium">
            {q.marks} mark{q.marks !== 1 ? "s" : ""}
          </span>
        )}
        {statusStyle && (
          <span className={`ml-auto inline-flex items-center gap-1.5 text-xs px-2.5 py-0.5 rounded-full border font-medium ${statusStyle.badge}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${statusStyle.dot}`} />
            {q.verification_status}
          </span>
        )}
      </div>

      {/* Question body */}
      <div className="px-5 py-4">
        <MathText
          text={q.question_text}
          block
          className="text-sm text-slate-800 leading-relaxed"
        />

        {/* Diagram */}
        {q.has_image && (
          <div className="mt-4 rounded-xl overflow-hidden border border-slate-200 bg-slate-50 w-full max-w-xl">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl(q.id)}
              alt={`Diagram for Q${q.question_number}`}
              className="w-full h-56 object-contain block p-2"
            />
          </div>
        )}
      </div>

      {/* Mark scheme */}
      {q.answer && (
        <div className="border-t border-slate-100">
          <button
            onClick={() => setShowMs(v => !v)}
            className="w-full flex items-center justify-between px-5 py-3 text-xs font-semibold text-amber-700 bg-amber-50 hover:bg-amber-100 transition-colors"
          >
            <span className="flex items-center gap-2">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
              </svg>
              Mark Scheme
            </span>
            <ChevronIcon open={showMs} />
          </button>

          {showMs && (
            <div className="px-5 py-4 bg-amber-50 border-t border-amber-100 space-y-2">
              <MathText text={q.answer} block className="text-sm text-slate-700 leading-relaxed" />
              {q.mark_breakdown && (
                <MathText text={q.mark_breakdown} block className="text-xs text-slate-500 leading-relaxed" />
              )}
              {q.additional_guidance && (
                <MathText text={q.additional_guidance} block className="text-xs text-slate-400 italic leading-relaxed" />
              )}
            </div>
          )}
        </div>
      )}

      {/* Generated answers */}
      {q.answers.length > 0 && (
        <div className="border-t border-slate-100">
          <button
            onClick={() => setShowAnswers(v => !v)}
            className="w-full flex items-center justify-between px-5 py-3 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 transition-colors"
          >
            <span className="flex items-center gap-2">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {q.answers.length} Generated Answers
            </span>
            <ChevronIcon open={showAnswers} />
          </button>

          {showAnswers && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-t border-slate-100">
                <thead>
                  <tr className="bg-slate-800 text-slate-200">
                    <th className="px-4 py-2.5 text-left font-semibold">Category</th>
                    <th className="px-4 py-2.5 text-left font-semibold">Answer</th>
                    <th className="px-4 py-2.5 text-center font-semibold w-20">Score</th>
                    <th className="px-4 py-2.5 text-center font-semibold w-20">Verdict</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {q.answers.map((a) => {
                    const verdict = a.verified === true ? "pass" : a.verified === false ? "fail" : null;
                    return (
                      <tr key={a.id} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-3 font-medium text-slate-700 whitespace-nowrap align-top">{a.category}</td>
                        <td className="px-4 py-3 text-slate-600 leading-relaxed align-top">
                          <MathText text={a.answer_text} />
                        </td>
                        <td className="px-4 py-3 text-center text-slate-700 font-mono align-top">
                          {a.awarded_marks != null ? `${a.awarded_marks}/${q.marks ?? "?"}` : "—"}
                        </td>
                        <td className="px-4 py-3 text-center align-top">
                          {verdict ? (
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold border ${VERDICT_STYLE[verdict]}`}>
                              {verdict}
                            </span>
                          ) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
