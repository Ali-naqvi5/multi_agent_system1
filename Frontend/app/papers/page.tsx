import Link from "next/link";
import { listPapers } from "@/lib/api";

export const dynamic = "force-dynamic";

const BOARD_COLORS: Record<string, string> = {
  edexcel: "bg-blue-100 text-blue-700",
  aqa:     "bg-purple-100 text-purple-700",
  ocr:     "bg-orange-100 text-orange-700",
  wjec:    "bg-teal-100 text-teal-700",
  ccea:    "bg-pink-100 text-pink-700",
};

function boardColor(board: string | null): string {
  return BOARD_COLORS[(board ?? "").toLowerCase()] ?? "bg-slate-100 text-slate-600";
}

export default async function PapersPage() {
  let papers;
  try {
    papers = await listPapers();
  } catch {
    return (
      <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-red-700 text-sm">
        Could not connect to the API server. Make sure it is running on{" "}
        <code className="font-mono bg-red-100 px-1 rounded">
          {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
        </code>
      </div>
    );
  }

  return (
    <div>
      {/* Page header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Past Papers</h1>
          <p className="mt-1 text-slate-500 text-sm">
            {papers.length} paper{papers.length !== 1 ? "s" : ""} processed and stored
          </p>
        </div>
        <Link
          href="/"
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl px-4 py-2.5 transition-colors shadow-sm"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          Run Pipeline
        </Link>
      </div>

      {papers.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-16 text-center shadow-sm">
          <div className="text-5xl mb-4">📋</div>
          <h3 className="text-lg font-semibold text-slate-700 mb-1">No papers yet</h3>
          <p className="text-slate-400 text-sm mb-6">Run the pipeline with a question paper and mark scheme to get started.</p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl px-5 py-2.5 transition-colors"
          >
            Run your first pipeline →
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {papers.map((p) => (
            <Link
              key={p.id}
              href={`/papers/${p.id}`}
              className="group bg-white border border-slate-200 rounded-2xl p-5 hover:shadow-md hover:border-blue-300 transition-all"
            >
              {/* Board badge + year */}
              <div className="flex items-center justify-between mb-3">
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full uppercase tracking-wide ${boardColor(p.board)}`}>
                  {p.board ?? "Unknown"}
                </span>
                <span className="text-xs text-slate-400 font-medium">{p.year ?? "—"}</span>
              </div>

              {/* Title */}
              <p className="font-bold text-slate-800 group-hover:text-blue-600 leading-snug text-base transition-colors">
                {[p.level, p.subject].filter(Boolean).join(" · ") || "Untitled Paper"}
              </p>

              {/* Subtitle */}
              {(p.paper_code || p.tier) && (
                <p className="text-sm text-slate-500 mt-0.5">
                  {p.paper_code ? `Paper ${p.paper_code}` : ""}
                  {p.paper_code && p.tier ? " · " : ""}
                  {p.tier ?? ""}
                </p>
              )}

              {/* Footer */}
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  {p.question_count} question{p.question_count !== 1 ? "s" : ""}
                </span>
                <span className="text-xs text-blue-500 font-medium group-hover:underline">View →</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
