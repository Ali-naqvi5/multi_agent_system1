import type { Metadata } from "next";
import "./globals.css";
import "katex/dist/katex.min.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "ExamEval — Past Paper AI",
  description: "Multi-agent past paper extraction and evaluation",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📋</text></svg>",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <header className="sticky top-0 z-50 bg-slate-900 shadow-lg">
          <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2.5 text-white font-bold text-lg tracking-tight flex-shrink-0">
              <span className="bg-blue-500 text-white rounded-lg w-7 h-7 flex items-center justify-center text-sm font-black">E</span>
              ExamEval
            </Link>
            <nav className="flex items-center gap-1 ml-4">
              <Link href="/" className="text-slate-300 hover:text-white hover:bg-slate-700 px-3 py-1.5 rounded-md text-sm font-medium transition-colors">
                Run Pipeline
              </Link>
              <Link href="/papers" className="text-slate-300 hover:text-white hover:bg-slate-700 px-3 py-1.5 rounded-md text-sm font-medium transition-colors">
                Browse Papers
              </Link>
            </nav>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
