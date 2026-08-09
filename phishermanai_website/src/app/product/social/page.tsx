import type { Metadata } from "next";

import { ChannelPage } from "@/components/product/channel-page";
import { Section, SectionHeading } from "@/components/site/section";
import { TerminalCard } from "@/components/site/terminal-card";
import { targetUsers } from "@/lib/content";

export const metadata: Metadata = {
  title: "Social & coordination",
  description:
    "AI-generated campaigns clustered by similarity and burst timing, then correlated against abnormal price and volume on the tickers actually named.",
};

const dashboards = [
  {
    path: "GET /api/v1/dashboard/broker",
    title: "Broker view",
    body: "Trending manipulated tickers and active campaigns, so impersonation of your own brand surfaces before the support queue does.",
  },
  {
    path: "GET /api/v1/dashboard/regulator",
    title: "Regulator view",
    body: "A cross-platform rollup with the most-impersonated issuers, every row carrying the source and date it was drawn from.",
  },
  {
    path: "GET /api/v1/coordination",
    title: "Campaign analysis",
    body: "Clustering across stored chatter, with the similarity and timing evidence attached to each cluster rather than reduced to a score.",
  },
];

export default function SocialChannelPage() {
  return (
    <ChannelPage id="social">
      <Section id="why-heuristic">
        <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16">
          <div>
            <SectionHeading
              eyebrow="Why this is a heuristic"
              title="A graph network trained on nothing"
              accent="is not more scientific than arithmetic you can explain."
              lead="The original plan called for a trained graph neural network over the account graph. There is no labelled bot dataset here to train one on."
            />
            <p className="copy mt-6">
              The choice was between a model whose weights nobody could account for and a method
              a regulator can be walked through in two minutes: these forty posts share 0.9
              TF-IDF similarity, they were published inside a 38-minute window, and the ticker
              they name moved 840% above its 30-day volume. Every step of that is inspectable.
            </p>
            <p className="copy mt-5">
              If labelled campaign data becomes available — the kind an exchange or a regulator
              holds — the heuristic is the baseline a trained model would have to beat, not
              something it replaces by default.
            </p>

            <div className="mt-10 space-y-5">
              {dashboards.map((dashboard) => (
                <div key={dashboard.path} className="border-l-2 border-primary/40 pl-5">
                  <p className="font-mono text-xs text-primary">{dashboard.path}</p>
                  <h3 className="mt-2 text-base font-medium">{dashboard.title}</h3>
                  <p className="copy mt-2 text-[1rem]">{dashboard.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="lg:sticky lg:top-28 lg:self-start">
            <TerminalCard label="POST /api/v1/verify" meta="200 · application/json">
              <pre className="overflow-x-auto font-mono text-[0.6875rem] leading-relaxed text-cream/80">
{`{
  "risk_score": 0.78,
  "band": "High",
  "headline": "Likely market propaganda —
     driven by phishing/scam language",
  "signals": [
    {
      "name": "text_phishing",
      "score": 0.999,
      "available": true,
      "summary": "phishing (99.9% confidence)"
    },
    {
      "name": "coordination",
      "score": 0.62,
      "available": true,
      "summary": "61 accounts, 38-minute burst"
    },
    {
      "name": "market_anomaly",
      "score": 0.0,
      "available": false,
      "error": "no tickers identified"
    }
  ]
}`}
              </pre>
              <p className="mt-4 font-serif text-xs leading-relaxed text-cream/45 italic">
                available: false means the detector was skipped or failed. Those are excluded
                from scoring and the remaining weights renormalised.
              </p>
            </TerminalCard>
          </div>
        </div>
      </Section>

      <Section tone="raised">
        <SectionHeading
          eyebrow="Who reads it"
          title="The same evidence,"
          accent="three different jobs."
        />
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {targetUsers.slice(1).map((user) => (
            <div key={user.name} className="rounded-xl border border-border bg-card p-6">
              <user.icon className="size-5 text-primary" aria-hidden />
              <h3 className="mt-4 text-lg font-medium">{user.name}</h3>
              <p className="copy mt-3 text-[1rem]">{user.needs}</p>
            </div>
          ))}
        </div>
      </Section>
    </ChannelPage>
  );
}
