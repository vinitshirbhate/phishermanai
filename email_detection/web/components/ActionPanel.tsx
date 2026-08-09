"use client";

import { useState } from "react";
import type { Action, VerdictResponse } from "@/lib/types";

const PRIORITY_STYLE: Record<string, string> = {
  IMMEDIATE: "border-red-300 bg-red-50",
  HIGH: "border-amber-300 bg-amber-50",
  MEDIUM: "border-slate-300 bg-slate-50",
  INFO: "border-emerald-300 bg-emerald-50",
};

function ContactBlock({ contact }: { contact: Record<string, any> }) {
  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-sm">
      <p className="font-semibold text-slate-900">{contact.entity}</p>
      <dl className="mt-2 space-y-1 text-slate-600">
        {contact.sebi_registration && (
          <div className="flex gap-2">
            <dt className="w-32 shrink-0 text-slate-500">SEBI registration</dt>
            <dd className="font-mono text-slate-800">{contact.sebi_registration}</dd>
          </div>
        )}
        {contact.registered_email && (
          <div className="flex gap-2">
            <dt className="w-32 shrink-0 text-slate-500">Registered email</dt>
            <dd className="break-all text-slate-800">{contact.registered_email}</dd>
          </div>
        )}
        {contact.registered_phone && (
          <div className="flex gap-2">
            <dt className="w-32 shrink-0 text-slate-500">Registered phone</dt>
            <dd className="text-slate-800">{contact.registered_phone}</dd>
          </div>
        )}
        {Array.isArray(contact.official_domains) && contact.official_domains.length > 0 && (
          <div className="flex gap-2">
            <dt className="w-32 shrink-0 text-slate-500">Official domains</dt>
            <dd className="text-slate-800">{contact.official_domains.join(", ")}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export default function ActionPanel({ result }: { result: VerdictResponse }) {
  const [copied, setCopied] = useState(false);
  const reports = result.evidence_summary?.reports;
  const cardUrl = result.warning_card_url ? `/api${result.warning_card_url}` : null;

  async function copyReport() {
    const text = reports?.prefilled_text ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="card overflow-hidden">
      <header className="border-b border-slate-200 px-5 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          What to do now
        </h2>
      </header>

      <div className="space-y-3 p-5">
        {result.recommended_actions.map((action: Action, i) => (
          <div
            key={i}
            className={`rounded-lg border p-4 ${PRIORITY_STYLE[action.priority] ?? PRIORITY_STYLE.MEDIUM}`}
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-semibold text-slate-900">{action.title}</h3>
              <span className="chip shrink-0 bg-white/70 text-slate-600">
                {action.priority}
              </span>
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{action.detail}</p>

            {action.contact && <ContactBlock contact={action.contact} />}

            {action.channel && (
              <a
                href={String(action.channel.url)}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-slate-900 underline underline-offset-2"
              >
                {String(action.channel.name)}
                {action.channel.helpline ? ` · call ${action.channel.helpline}` : ""}
              </a>
            )}
          </div>
        ))}

        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
          {cardUrl && (
            <a href={cardUrl} download className="btn-primary">
              Download warning card
            </a>
          )}
          {reports?.prefilled_text && (
            <button onClick={copyReport} className="btn-ghost">
              {copied ? "Copied to clipboard" : "Copy prefilled report"}
            </button>
          )}
        </div>

        {reports?.recommended_route && (
          <p className="text-xs text-slate-500">
            Report routed to <strong>{String(reports.recommended_route).replace("_", " ")}</strong>{" "}
            based on whether the entity is SEBI-registered.
          </p>
        )}
      </div>
    </section>
  );
}
