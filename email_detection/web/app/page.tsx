"use client";

import { useCallback, useEffect, useState } from "react";
import ActionPanel from "@/components/ActionPanel";
import DropZone from "@/components/DropZone";
import ReasonList from "@/components/ReasonList";
import StatsTab from "@/components/StatsTab";
import TamperView from "@/components/TamperView";
import VerdictCard from "@/components/VerdictCard";
import type { VerdictResponse } from "@/lib/types";

type Tab = "verify" | "clusters";

export default function Home() {
  const [tab, setTab] = useState<Tab>("verify");
  const [result, setResult] = useState<VerdictResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function post(form: FormData) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/verify", { method: "POST", body: form });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail ?? `Request failed (${res.status})`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit({ file, text }: { file?: File; text?: string }) {
    const form = new FormData();
    if (file) {
      form.append("file", file);
      // Keep a local preview so the tamper view can draw the red box on it.
      setImageUrl(file.type.startsWith("image/") ? URL.createObjectURL(file) : null);
    } else if (text) {
      form.append("text", text);
      setImageUrl(null);
    }
    form.append("channel", "WEB");
    await post(form);
  }

  const handleExample = useCallback(async (fixture: string) => {
    setBusy(true);
    setError(null);
    setImageUrl(null);
    try {
      const res = await fetch(`/api/demo/verify/${encodeURIComponent(fixture)}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Could not load the example (${res.status})`);
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the example.");
    } finally {
      setBusy(false);
    }
  }, []);

  // Deep link straight to a worked example: /?demo=tampered_01.eml
  // Handy in a live demo -- each scenario gets its own URL, so there is no
  // clicking around between them -- and it makes the UI screenshot-testable.
  useEffect(() => {
    const demo = new URLSearchParams(window.location.search).get("demo");
    if (demo) void handleExample(demo);
  }, [handleExample]);

  return (
    <div className="space-y-6">
      <nav className="flex gap-1 border-b border-slate-200">
        {(
          [
            ["verify", "Verify a message"],
            ["clusters", "Fraud clusters"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === key
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "clusters" ? (
        <StatsTab />
      ) : (
        <div className="space-y-6">
          <DropZone onSubmit={handleSubmit} onExample={handleExample} busy={busy} />

          {error && (
            <div className="card border-red-300 bg-red-50 px-5 py-4 text-sm text-red-800">
              {error}
              <p className="mt-1 text-xs text-red-700">
                Is the API running? Start it with{" "}
                <code className="font-mono">uvicorn api.main:app</code>.
              </p>
            </div>
          )}

          {busy && (
            <div className="card px-5 py-8 text-center text-sm text-slate-500">
              Running four chokepoint checks and cross-checking exchange filings…
            </div>
          )}

          {result && !busy && (
            <div className="space-y-5">
              <VerdictCard result={result} />

              {/* The demo moment: only rendered when a field actually differs. */}
              {result.field_comparisons?.some((c) => c.match === false) && (
                <TamperView
                  comparisons={result.field_comparisons}
                  filing={result.matched_filing}
                  imageUrl={imageUrl}
                />
              )}

              <ReasonList reasons={result.reasons} />
              <ActionPanel result={result} />

              {result.matched_filing && (
                <section className="card p-5">
                  <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-600">
                    Matched exchange filing
                  </h2>
                  <p className="text-sm text-slate-800">
                    {result.matched_filing.company_name} ·{" "}
                    {result.matched_filing.filing_type} ·{" "}
                    {result.matched_filing.filing_date?.slice(0, 10)} ·{" "}
                    {result.matched_filing.exchange}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Matched by {result.matched_filing.ranking_method} (tier{" "}
                    {result.matched_filing.tier}) from{" "}
                    {result.matched_filing.candidates_considered} candidate filings.
                  </p>
                  {result.matched_filing.notes?.map((n, i) => (
                    <p key={i} className="mt-1 text-xs text-slate-500">
                      {n}
                    </p>
                  ))}
                  {result.matched_filing.pdf_url && (
                    <a
                      href={result.matched_filing.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-block text-sm font-medium text-slate-900 underline underline-offset-2"
                    >
                      Open the filing on the exchange
                    </a>
                  )}
                </section>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
