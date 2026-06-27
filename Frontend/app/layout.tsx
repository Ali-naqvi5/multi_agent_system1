import type { Metadata } from "next";
import "app./globals.css";

export const metadata: Metadata = {
  title: "Past Paper System",
  description: "Multi-agent past paper extraction and evaluation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
          <span className="font-bold text-blue-700 text-lg">Past Paper System</span>
          <a href="/" className="text-sm text-gray-600 hover:text-blue-600">Run Pipeline</a>
          <a href="/papers" className="text-sm text-gray-600 hover:text-blue-600">Browse Papers</a>
        </nav>
        <main className="max-w-5xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
