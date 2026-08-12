"use client";

import { ArrowUpRight, Ban, Building2, Flag, Phone, ShieldCheck } from "lucide-react";

import type { EngineAction, EngineVerdictResponse } from "@/lib/engine-types";
import { cn } from "@/lib/utils";

/**
 * Where to take a verdict next.
 *
 * The destinations come from the engine, not from this file. It already routes
 * on whether money has actually been lost — the cybercrime helpline inside the
 * golden hour, SCORES for a registered intermediary, a takedown report for an
 * unregistered one. Hardcoding a single "report to SEBI" link here would send
 * people to the wrong place in the case that matters most.
 */

const typeIcon: Record<string, typeof Flag> = {
  DO_NOT: Ban,
  VERIFY: ShieldCheck,
  SAFE_TO_READ: ShieldCheck,
  OFFICIAL_CONTACT: Building2,
  REPORT: Flag,
  SHARE: ArrowUpRight,
};

const priorityClass: Record<string, string> = {
  IMMEDIATE: "border-verdict-fraud/40 bg-verdict-fraud/10 text-verdict-fraud",
  HIGH: "border-verdict-tampered/40 bg-verdict-tampered/10 text-verdict-tampered",
  MEDIUM: "border-verdict-quiet/40 bg-verdict-quiet/10 text-verdict-quiet",
  INFO: "border-verdict-verified/40 bg-verdict-verified/10 text-verdict-verified",
};

function channelOf(action: EngineAction) {
  const channel = action.channel as Record<string, unknown> | null;
  if (!channel || typeof channel.url !== "string") return null;
  return {
    name: typeof channel.name === "string" ? channel.name : channel.url,
    url: channel.url,
    helpline: typeof channel.helpline === "string" ? channel.helpline : null,
    useWhen: typeof channel.use_when === "string" ? channel.use_when : null,
  };
}

function contactRows(action: EngineAction): [string, string][] {
  const contact = action.contact as Record<string, unknown> | null;
  if (!contact) return [];
  return Object.entries(contact)
    .filter(([, value]) => typeof value === "string" || typeof value === "number")
    .map(([key, value]) => [key.replace(/_/g, " "), String(value)]);
}

export function EscalationPanel({ result }: { result: EngineVerdictResponse }) {
  if (result.recommended_actions.length === 0) return null;

  return (
    <section className="rounded-xl border border-border bg-card p-5 sm:p-6">
      <h2 className="text-lg font-medium">What to do next</h2>
      <p className="copy mt-2 text-[1rem]">
        Chosen by the engine for this verdict. Nothing here is sent or reported on your
        behalf — every step is yours to take.
      </p>

      <ul className="mt-6 space-y-4">
        {result.recommended_actions.map((action) => {
          const Icon = typeIcon[action.type] ?? Flag;
          const channel = channelOf(action);
          const contact = contactRows(action);

          return (
            <li key={`${action.type}-${action.title}`} className="rounded-lg border border-border p-4">
              <div className="flex flex-wrap items-center gap-2.5">
                <Icon className="size-4 shrink-0 text-primary" aria-hidden />
                <span
                  className={cn(
                    "mono-label rounded-full border px-2 py-0.5",
                    priorityClass[action.priority] ?? priorityClass.MEDIUM,
                  )}
                >
                  {action.priority}
                </span>
                <span className="mono-label text-foreground/35">
                  {action.type.replace(/_/g, " ").toLowerCase()}
                </span>
              </div>

              <p className="mt-3 text-[0.9375rem] font-medium">{action.title}</p>
              <p className="mt-1.5 font-serif text-[0.9375rem] leading-relaxed text-foreground/65">
                {action.detail}
              </p>

              {channel ? (
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4">
                  <a
                    href={channel.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
                  >
                    {channel.name}
                    <ArrowUpRight className="size-3.5" aria-hidden />
                  </a>
                  {channel.helpline ? (
                    <a
                      href={`tel:${channel.helpline}`}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3.5 py-2 text-sm font-medium transition-colors hover:bg-muted"
                    >
                      <Phone className="size-3.5" aria-hidden />
                      Call {channel.helpline}
                    </a>
                  ) : null}
                  {channel.useWhen ? (
                    <span className="font-serif text-xs text-foreground/50 italic">
                      {channel.useWhen}
                    </span>
                  ) : null}
                </div>
              ) : null}

              {contact.length > 0 ? (
                <dl className="mt-4 space-y-1.5 border-t border-border pt-4">
                  <p className="mono-label text-foreground/35">verified official contact</p>
                  {contact.map(([key, value]) => (
                    <div key={key} className="flex flex-wrap gap-x-3">
                      <dt className="mono-label w-24 shrink-0 pt-0.5 text-foreground/35">{key}</dt>
                      <dd className="font-mono text-xs break-all text-foreground/70">{value}</dd>
                    </div>
                  ))}
                  <p className="pt-2 font-serif text-xs text-foreground/50 italic">
                    These come from SEBI&rsquo;s register and the verified domain map. Do not use
                    a helpline found through a search engine — fraudulent numbers are placed
                    there deliberately.
                  </p>
                </dl>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
