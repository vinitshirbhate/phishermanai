import { TerminalCard, TerminalRow } from "@/components/site/terminal-card";
import { lanes } from "@/lib/content";
import { cn } from "@/lib/utils";

/** Email — the message's journey, with the branch that answers early. */
function EmailDiagram() {
  const nodes = [
    { label: "ingest", state: "done" },
    { label: "clean · mask", state: "done" },
    { label: "dkim gate", state: "active" },
    { label: "4 checks", state: "queued" },
    { label: "filing", state: "queued" },
    { label: "verdict", state: "queued" },
  ] as const;

  return (
    <TerminalCard label="KILL CHAIN" meta="one message · six stages">
      <div className="space-y-3">
        {nodes.map((node, index) => (
          <div key={node.label} className="flex items-center gap-3">
            <span
              className={cn(
                "grid size-6 shrink-0 place-items-center rounded-full border font-mono text-[0.625rem]",
                node.state === "active"
                  ? "animate-pulse-node border-primary bg-primary/25 text-primary"
                  : node.state === "done"
                    ? "border-cream/25 bg-cream/10 text-cream/70"
                    : "border-cream/12 text-cream/30",
              )}
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <span
              className={cn(
                "font-mono text-[0.8125rem] tracking-wide",
                node.state === "active"
                  ? "text-primary"
                  : node.state === "done"
                    ? "text-cream/70"
                    : "text-cream/30",
              )}
            >
              {node.label}
            </span>
            <span
              className={cn(
                "dashed-rule h-px flex-1",
                node.state === "queued" ? "text-cream/12" : "text-cream/25",
              )}
              aria-hidden
            />
            <span
              className={cn(
                "mono-label",
                node.state === "active"
                  ? "text-primary"
                  : node.state === "done"
                    ? "text-verdict-verified"
                    : "text-cream/25",
              )}
            >
              {node.state === "active" ? "running" : node.state === "done" ? "ok" : "queued"}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-5 rounded-lg border border-verdict-verified/25 bg-verdict-verified/8 px-3 py-2.5">
        <p className="mono-label text-verdict-verified">branch · sender proven</p>
        <p className="mt-1.5 font-mono text-[0.8125rem] text-cream/70">
          83% exit here → VERIFIED in 10 ms
        </p>
      </div>
    </TerminalCard>
  );
}

/** Voice — transcript, spoof score, and the check that does not exist. */
function VoiceDiagram() {
  const bars = [8, 22, 14, 31, 19, 27, 11, 34, 17, 25, 9, 29, 15, 21, 12, 33, 18, 24, 10, 28];

  return (
    <TerminalCard label="VOICE PIPELINE" meta="16 kHz mono · 3.6 MB">
      <div className="flex h-16 items-center gap-[3px]" aria-hidden>
        {bars.map((height, index) => (
          <span
            key={index}
            className={cn(
              "flex-1 rounded-full",
              index > 12 ? "bg-primary/70" : "bg-cream/25",
            )}
            style={{ height: `${(height / 34) * 100}%` }}
          />
        ))}
      </div>
      <p className="mt-3 font-mono text-[0.6875rem] text-cream/35">
        00:00 ─────────────────────── 02:14
      </p>

      <div className="mt-5 rounded-lg border border-cream/12 bg-cream/4 px-3.5 py-3">
        <p className="mono-label text-cream/40">transcript · whisper</p>
        <p className="mt-2 font-mono text-[0.75rem] leading-relaxed text-cream/75">
          “…this is the compliance desk, we need the transfer confirmed before market close, just
          read back the OTP…”
        </p>
      </div>

      <div className="mt-4">
        <TerminalRow label="synthetic artefacts" value="0.91" state="fail" />
        <TerminalRow label="text rules" value="outbound OTP · sev 5" state="fail" />
        <TerminalRow label="claimed source" value="not in registry" state="warn" />
        <TerminalRow label="speaker match" value="not determined" state="muted" />
      </div>

      <p className="mt-3 font-serif text-xs leading-relaxed text-cream/45 italic">
        The system can say the audio is synthetic. It cannot say whose voice it is — and it does
        not pretend otherwise.
      </p>
    </TerminalCard>
  );
}

/** Video — per-frame scores, with the honest unavailable state. */
function VideoDiagram() {
  const frames = [0.12, 0.34, 0.71, 0.88, 0.93, 0.79, 0.44, 0.21];

  return (
    <TerminalCard label="FRAME ANALYSIS" meta="8 sampled · 1 of 2 detectors">
      <div className="grid grid-cols-8 gap-1.5">
        {frames.map((score, index) => (
          <div key={index} className="space-y-1.5">
            <div
              className={cn(
                "grid aspect-square place-items-center rounded border font-mono text-[0.5625rem]",
                score > 0.7
                  ? "border-verdict-fraud/40 bg-verdict-fraud/15 text-verdict-fraud"
                  : score > 0.4
                    ? "border-verdict-tampered/40 bg-verdict-tampered/12 text-verdict-tampered"
                    : "border-cream/15 bg-cream/5 text-cream/40",
              )}
            >
              {String(index + 1).padStart(2, "0")}
            </div>
            <p className="text-center font-mono text-[0.5625rem] text-cream/40">
              {score.toFixed(2)}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-5">
        <TerminalRow label="frame deepfake" value="0.93 peak" state="fail" />
        <TerminalRow label="audio track" value="0.88 synthetic" state="fail" />
        <TerminalRow label="content credentials" value="none present" state="muted" />
        <TerminalRow label="generalisation" value="unproven on unseen" state="warn" />
      </div>

      <p className="mt-3 font-serif text-xs leading-relaxed text-cream/45 italic">
        Absent provenance metadata is not evidence of anything — almost no video carries it yet.
      </p>
    </TerminalCard>
  );
}

/** Social — a cluster, its burst, and whether the market moved. */
function SocialDiagram() {
  const posts = [
    { handle: "@alpha_calls_91", sim: 0.94 },
    { handle: "@vip_wealth_ind", sim: 0.91 },
    { handle: "@nifty_insider7", sim: 0.89 },
    { handle: "@sure_shot_bse", sim: 0.87 },
  ];

  return (
    <TerminalCard label="COORDINATION" meta="tf-idf + burst timing">
      <div className="space-y-2">
        {posts.map((post) => (
          <div
            key={post.handle}
            className="flex items-center gap-3 rounded-lg border border-cream/10 bg-cream/4 px-3 py-2"
          >
            <span className="font-mono text-[0.75rem] text-cream/75">{post.handle}</span>
            <span className="dashed-rule h-px flex-1 text-cream/20" aria-hidden />
            <span className="font-mono text-[0.75rem] text-primary">
              sim {post.sim.toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 rounded-lg border border-cream/12 bg-cream/4 px-3.5 py-3">
        <p className="mono-label text-cream/40">posting burst</p>
        <div className="mt-2.5 flex h-8 items-end gap-1" aria-hidden>
          {[4, 6, 5, 7, 42, 88, 76, 51, 12, 8, 5, 6].map((height, index) => (
            <span
              key={index}
              className={cn(
                "flex-1 rounded-sm",
                height > 40 ? "bg-primary" : "bg-cream/20",
              )}
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
        <p className="mt-2 font-mono text-[0.625rem] text-cream/35">
          214 posts in 38 minutes, from 61 accounts
        </p>
      </div>

      <div className="mt-4">
        <TerminalRow label="ticker named" value="one small-cap" state="neutral" />
        <TerminalRow label="volume vs 30d" value="+840%" state="fail" />
        <TerminalRow label="method" value="heuristic, explainable" state="muted" />
      </div>
    </TerminalCard>
  );
}

/** Web — four lanes that know nothing about each other, merged. */
function WebDiagram() {
  const readings = [
    { state: "fail", value: "collision" },
    { state: "warn", value: "off-domain" },
    { state: "muted", value: "not running" },
    { state: "fail", value: "apk offered" },
  ] as const;

  return (
    <TerminalCard label="FOUR LANES" meta="merge · floor-only">
      <div className="space-y-2">
        {lanes.map((lane, index) => (
          <div
            key={lane.name}
            className="flex items-center justify-between gap-3 rounded-lg border border-cream/10 bg-cream/4 px-3 py-2.5"
          >
            <div className="flex items-center gap-2.5">
              <lane.icon className="size-4 text-primary" aria-hidden />
              <span className="font-mono text-[0.8125rem] text-cream/85">{lane.name}</span>
            </div>
            <span
              className={cn(
                "font-mono text-[0.75rem]",
                readings[index].state === "fail"
                  ? "text-verdict-fraud"
                  : readings[index].state === "warn"
                    ? "text-verdict-tampered"
                    : "text-cream/35",
              )}
            >
              {readings[index].value}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-2" aria-hidden>
        <span className="dashed-rule h-px flex-1 text-cream/20" />
        <span className="mono-label text-cream/35">merge signals</span>
        <span className="dashed-rule h-px flex-1 text-cream/20" />
      </div>

      <div className="mt-3 rounded-lg border border-verdict-fraud/30 bg-verdict-fraud/10 px-3 py-3">
        <p className="mono-label text-verdict-fraud">low trust</p>
        <p className="mt-1.5 font-mono text-[0.8125rem] leading-relaxed text-cream/75">
          INA000000383 is registered to V R WEALTH ADVISORS PRIVATE LIMITED, not to this sender
        </p>
        <p className="mt-2 font-mono text-[0.6875rem] text-cream/35">
          register data as of 2026-08-06
        </p>
      </div>
    </TerminalCard>
  );
}

/** The fused view — every channel's signal, and the ones that could not run. */
export function FusionDiagram() {
  const rows = [
    { name: "text_phishing", score: 0.99, available: true },
    { name: "voice_spoof", score: 0.91, available: true },
    { name: "video_deepfake", score: 0, available: false },
    { name: "source_untrusted", score: 0.95, available: true },
    { name: "coordination", score: 0.31, available: true },
    { name: "market_anomaly", score: 0, available: false },
  ];

  return (
    <TerminalCard label="SIGNAL FUSION" meta="weights renormalised">
      <div className="space-y-2.5">
        {rows.map((row) => (
          <div key={row.name}>
            <div className="flex items-baseline justify-between gap-3">
              <span
                className={cn(
                  "font-mono text-[0.75rem]",
                  row.available ? "text-cream/80" : "text-cream/30",
                )}
              >
                {row.name}
              </span>
              <span
                className={cn(
                  "font-mono text-[0.75rem]",
                  row.available ? "text-cream/55" : "text-cream/25",
                )}
              >
                {row.available ? row.score.toFixed(2) : "unavailable"}
              </span>
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-cream/10">
              <div
                className={cn("h-full rounded-full", row.available ? "bg-primary" : "bg-cream/15")}
                style={{ width: `${(row.available ? row.score : 0.04) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5">
        <TerminalRow label="risk score" value="0.88" state="fail" />
        <TerminalRow label="band" value="High" state="fail" />
        <TerminalRow label="excluded" value="2 detectors" state="muted" />
      </div>
      <p className="mt-3 font-serif text-xs leading-relaxed text-cream/45 italic">
        A detector that could not run is removed from the mean, never counted as evidence of
        innocence.
      </p>
    </TerminalCard>
  );
}

export function ChannelDiagram({ variant }: { variant: string }) {
  switch (variant) {
    case "voice":
      return <VoiceDiagram />;
    case "video":
      return <VideoDiagram />;
    case "social":
      return <SocialDiagram />;
    case "web":
      return <WebDiagram />;
    default:
      return <EmailDiagram />;
  }
}
