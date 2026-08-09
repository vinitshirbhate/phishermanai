"use client";

import { useEffect, useState } from "react";
import { VERDICT_STYLES, type StatsResponse, type VerdictKind } from "@/lib/types";

/**
 * The regulator-facing view, deliberately read-only.
 *
 * The point it makes: identical content reported many times is ONE fraud
 * campaign, not many tickets. Grouping by content fingerprint is what turns a
 * queue of individual complaints into a picture of how far a single piece of
 * fraud has travelled.
 *
 * This is an aggregation over our own verifications. It does not pretend to be
 * integrated with SEBI or any exchange.
 */
export default function StatsTab() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="card border-red-300 bg-red-50 px-5 py-4 text-sm text-red-800">
        Could not load statistics: {error}
      </div>
    );
  }
  if (!stats) {
    return <div className="card px-5 py-8 text-center text-sm text-slate-500">Loading…</div>;
  }

  return (
    <div className="space-y-5">
      <section className="grid gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Verifications
          </div>
          <div className="mt-1 text-3xl font-bold text-slate-900">
            {stats.total_verifications.toLocaleString()}
          </div>
        </div>
        <div className="card p-5">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Mean latency
          </div>
          <div className="mt-1 text-3xl font-bold text-slate-900">
            {stats.mean_latency_ms.toFixed(0)}
            <span className="text-lg font-normal text-slate-500">ms</span>
          </div>
        </div>
        <div className="card p-5">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Filings corpus
          </div>
          <div className="mt-1 text-3xl font-bold text-slate-900">
            {stats.corpus.filings.toLocaleString()}
          </div>
          <div className="text-xs text-slate-500">
            {stats.corpus.entities.toLocaleString()} entities ·{" "}
            {stats.corpus.domains} mapped domains
          </div>
        </div>
      </section>

      <section className="card overflow-hidden">
        <header className="border-b border-slate-200 px-5 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
            Verdicts issued
          </h2>
        </header>
        <div className="grid grid-cols-2 divide-x divide-slate-200 sm:grid-cols-4">
          {(["GENUINE", "TAMPERED", "UNVERIFIED", "FRAUDULENT"] as VerdictKind[]).map((v) => (
            <div key={v} className="px-4 py-4">
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${VERDICT_STYLES[v].dot}`} />
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {VERDICT_STYLES[v].label}
                </span>
              </div>
              <div className="mt-1 text-2xl font-bold text-slate-900">
                {stats.by_verdict[v] ?? 0}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card overflow-hidden">
        <header className="border-b border-slate-200 px-5 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
            Fraud campaigns (clustered by content fingerprint)
          </h2>
        </header>
        {stats.fraud_clusters.length === 0 ? (
          <p className="px-5 py-6 text-sm text-slate-500">
            No repeated content yet. A cluster appears when the same message is
            submitted more than once.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-5 py-2 font-medium">Fingerprint</th>
                <th className="px-5 py-2 font-medium">Impersonated</th>
                <th className="px-5 py-2 font-medium">Domain</th>
                <th className="px-5 py-2 text-right font-medium">Reports</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {stats.fraud_clusters.map((c) => (
                <tr key={c.fingerprint}>
                  <td className="px-5 py-3 font-mono text-xs text-slate-500">
                    {c.fingerprint}
                  </td>
                  <td className="px-5 py-3 text-slate-800">{c.claimed_entity ?? "—"}</td>
                  <td className="px-5 py-3 text-slate-600">{c.top_domain ?? "—"}</td>
                  <td className="px-5 py-3 text-right">
                    <span className="chip bg-red-100 text-red-800">
                      {c.report_count} reports
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          Each row is one piece of content reported multiple times — one campaign,
          not {stats.fraud_clusters.reduce((n, c) => n + c.report_count, 0)} separate
          incidents.
        </p>
      </section>

      {stats.top_spoofed_entities.length > 0 && (
        <section className="card overflow-hidden">
          <header className="border-b border-slate-200 px-5 py-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
              Most impersonated entities
            </h2>
          </header>
          <ul className="divide-y divide-slate-100">
            {stats.top_spoofed_entities.map((e) => (
              <li key={e.entity} className="flex justify-between px-5 py-2.5 text-sm">
                <span className="text-slate-800">{e.entity}</span>
                <span className="font-medium text-slate-500">{e.count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
