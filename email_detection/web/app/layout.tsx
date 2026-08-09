import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PhishermanAI — verify financial messages",
  description:
    "Check whether a financial message is genuine, tampered, unverifiable or fraudulent — with visible reasons.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <div>
              <h1 className="text-lg font-bold tracking-tight text-slate-900">
                PhishermanAI
              </h1>
              <p className="text-xs text-slate-500">
                Verification for Indian retail investors · SEBI Problem Statement 1
              </p>
            </div>
            <a
              href="/api/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-slate-500 underline underline-offset-2 hover:text-slate-900"
            >
              API docs
            </a>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-5xl px-6 pb-10 pt-4 text-xs leading-relaxed text-slate-400">
          PhishermanAI checks four fraud chokepoints and cross-checks content against
          exchange filings. It covers listed-company corporate actions; it is not a
          substitute for confirming directly with your broker or the company.
        </footer>
      </body>
    </html>
  );
}
