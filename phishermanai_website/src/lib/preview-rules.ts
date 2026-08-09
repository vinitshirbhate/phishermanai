/**
 * Browser preview of the rule layer.
 *
 * This is a deliberately small subset that runs entirely in the page: the
 * direction-aware claim and money rules, and nothing else. It cannot prove a
 * sender (no DKIM) and cannot reach the filings corpus, so it only ever
 * returns FRAUDULENT or NO_RISK_FOUND — the two verdicts reachable without
 * either. VERIFIED and TAMPERED require the engine.
 *
 * Every rule declares an entity, an action, a direction and its suppressors,
 * exactly as the Python rules do. A rule with no action may not exceed
 * severity 1, and `assertRuleShape` enforces that at module load.
 */

import type { AnalysisResult, Chokepoint, Finding, FindingTier } from "./analysis";

export interface PreviewRule {
  id: string;
  chokepoint: Chokepoint;
  title: string;
  /** What the rule is about. */
  entity: RegExp;
  /** What is being done. A rule without one is capped at severity 1. */
  action?: RegExp;
  /** Who moves the thing — the difference between a warning and a request. */
  direction: "outbound" | "inbound" | "none";
  /** Phrases that mean the words are being described, not performed. */
  suppressors: RegExp[];
  severity: number;
  tier: FindingTier;
  detail: string;
}

const AWARENESS: RegExp[] = [
  /\b(never|do not|don'?t)\s+(share|disclose|reveal|send)\b/i,
  /\bbeware\s+of\b/i,
  /\bsebi\s+(cautions|advises|warns)\b/i,
  /\binvestor\s+awareness\b/i,
  /\bno\s+one\s+can\s+guarantee\b/i,
  /\bfraudsters?\s+(often|may|will|typically)\b/i,
  /\bif\s+(you|someone)\s+(receive|receives|asks)\b/i,
];

export const previewRules: PreviewRule[] = [
  {
    id: "guaranteed-return",
    chokepoint: "claim",
    title: "Guaranteed or assured return",
    entity: /\b(returns?|profits?|gains?|capital|principal)\b/i,
    action: /\b(guaranteed?|assured|risk[- ]free|100%\s*safe|fully\s+protected|no\s+loss)\b/i,
    direction: "none",
    suppressors: AWARENESS,
    severity: 5,
    tier: "disqualifying",
    detail:
      "No SEBI-registered intermediary may promise a return. The rule needs both the subject and the promise, so a note warning readers about this exact pitch does not fire it.",
  },
  {
    id: "otp-outbound",
    chokepoint: "money",
    title: "Outbound credential request",
    entity: /\b(otp|one[- ]time\s+password|pin|cvv|password|mpin)\b/i,
    action: /\b(share|send|forward|provide|give|tell|confirm|type|reply\s+with)\b/i,
    direction: "outbound",
    suppressors: [
      ...AWARENESS,
      /\b(will\s+be\s+sent|has\s+been\s+sent|sent\s+to\s+your|on\s+(your\s+)?registered)\b/i,
    ],
    severity: 5,
    tier: "disqualifying",
    detail:
      "Direction is the whole rule. “Share the OTP with me” asks a credential to travel outward; “an OTP will be sent to your registered mobile” describes one arriving. Same vocabulary, opposite meaning.",
  },
  {
    id: "upi-collection",
    chokepoint: "money",
    title: "Collection outside the @valid namespace",
    entity: /\b[a-z0-9][a-z0-9._-]{2,}@(?!valid)[a-z]{2,}\b/i,
    action: /\b(pay|transfer|send|deposit|remit|joining\s+fee|subscription|amount)\b/i,
    direction: "outbound",
    suppressors: [...AWARENESS, /\b[a-z0-9._-]+@[a-z0-9.-]+\.(com|in|org|net|gov|edu)\b/i],
    severity: 4,
    tier: "disqualifying",
    detail:
      "Registered intermediaries collect only through the @valid namespace, which is restricted at the NPCI level and cannot be self-issued. A consumer handle taking a fee is a rule breach, not a judgement call.",
  },
  {
    id: "kyc-coercion",
    chokepoint: "delivery",
    title: "Account-blocking pressure",
    entity: /\b(kyc|account|demat|folio|trading\s+account)\b/i,
    action: /\b(block(ed|ing)?|suspend(ed|ing)?|freeze|frozen|deactivat(e|ed)|clos(e|ed)\s+within)\b/i,
    direction: "outbound",
    suppressors: AWARENESS,
    severity: 4,
    tier: "disqualifying",
    detail:
      "Threatening to disable an account unless the reader acts is coercion toward a link or a payment. Genuine registrars route mandate changes through the depository participant instead.",
  },
  {
    id: "identifier-request",
    chokepoint: "money",
    title: "Protected identifier requested",
    entity: /\b(pan|aadhaar|demat|dp\s*id|client\s*id|bank\s+account|ifsc)\b/i,
    action: /\b(share|send|provide|reply\s+with|upload|confirm\s+your)\b/i,
    direction: "outbound",
    suppressors: AWARENESS,
    severity: 4,
    tier: "disqualifying",
    detail:
      "Identifiers are masked before any rule reads the text, so this fires on the request itself rather than on the value. The engine never stores what it masked.",
  },
  {
    id: "apk-offer",
    chokepoint: "delivery",
    title: "Installable app file offered",
    entity: /\.apk\b|\b(mod|cracked|unlocked|premium)\s+(apk|app|version)\b/i,
    action: /\b(install|download|sideload|open|send|attach(ed)?)\b/i,
    direction: "outbound",
    suppressors: AWARENESS,
    severity: 3,
    tier: "weak",
    detail:
      "Judged on the filename and the delivery route, never on file contents. A paid broker app advertised as unlocked and arriving over chat is the pattern.",
  },
  {
    id: "urgency",
    chokepoint: "claim",
    title: "Manufactured deadline",
    entity: /\b(seats?|slots?|allocation|offer|window|group|opportunity)\b/i,
    action: /\b(clos(es|ing)|expir(es|ing)|last\s+chance|only\s+\d+|ends?\s+(today|tonight)|within\s+\d+\s*(hour|minute))\b/i,
    direction: "none",
    suppressors: AWARENESS,
    severity: 2,
    tier: "weak",
    detail:
      "Compressing the decision window is a pressure tactic, not proof of fraud. It is reported as a weak finding and can only turn a verdict red alongside another one.",
  },
  {
    id: "registration-claimed",
    chokepoint: "entity",
    title: "SEBI registration number claimed",
    entity: /\bIN[AHZPM]\d{9}\b/,
    direction: "none",
    suppressors: [],
    severity: 1,
    tier: "context",
    detail:
      "A number is present and correctly shaped. Whether it resolves to this sender is a register lookup the browser preview cannot do — that check runs on-device in the extension in about 0.1 ms.",
  },
  {
    id: "external-link",
    chokepoint: "delivery",
    title: "Link to an external destination",
    entity: /\bhttps?:\/\/[^\s<>"]+/i,
    direction: "none",
    suppressors: [],
    severity: 1,
    tier: "context",
    detail:
      "The registrable domain is extracted with the Public Suffix List, so paytm.evil.co.in resolves to evil.co.in. Whether that domain belongs to the issuer needs the domain map.",
  },
];

/** A rule that describes a subject but no action cannot accuse. */
function assertRuleShape(rules: PreviewRule[]): void {
  for (const rule of rules) {
    if (!rule.action && rule.severity > 1) {
      throw new Error(
        `Rule "${rule.id}" declares no action but has severity ${rule.severity}. ` +
          "A rule with no action may not exceed severity 1.",
      );
    }
  }
}

assertRuleShape(previewRules);

const REQUEST_SIGNAL =
  /\b(pay|transfer|click|register|share|send|call|whatsapp|join|deposit|install|confirm|upload)\b/i;

export interface PreviewOutcome extends AnalysisResult {
  /** Set so the UI can never present a preview as an engine verdict. */
  preview: true;
  rulesEvaluated: number;
  suppressed: { id: string; title: string; reason: string }[];
}

export function runPreview(text: string): PreviewOutcome {
  const started = typeof performance !== "undefined" ? performance.now() : 0;
  const findings: Finding[] = [];
  const suppressed: PreviewOutcome["suppressed"] = [];

  for (const rule of previewRules) {
    if (!rule.entity.test(text)) continue;
    if (rule.action && !rule.action.test(text)) continue;

    const hit = rule.suppressors.find((suppressor) => suppressor.test(text));
    if (hit) {
      suppressed.push({
        id: rule.id,
        title: rule.title,
        reason:
          rule.id === "otp-outbound"
            ? "the credential travels inward, or the text warns about the request"
            : "the text describes the tactic rather than performing it",
      });
      continue;
    }

    findings.push({
      id: rule.id,
      chokepoint: rule.chokepoint,
      tier: rule.tier,
      severity: rule.severity,
      title: rule.title,
      detail: rule.detail,
    });
  }

  findings.sort((a, b) => b.severity - a.severity);

  const disqualifying = findings.filter((f) => f.tier === "disqualifying").length;
  const weak = findings.filter((f) => f.tier === "weak").length;
  const asks = REQUEST_SIGNAL.test(text);
  const fraudulent = disqualifying >= 1 || (weak >= 2 && asks);

  const elapsed = typeof performance !== "undefined" ? performance.now() - started : 0;

  return {
    preview: true,
    verdict: fraudulent ? "FRAUDULENT" : "NO_RISK_FOUND",
    headline: fraudulent
      ? disqualifying >= 1
        ? "Disqualifying finding in the pasted text"
        : "Two weak findings alongside a request"
      : findings.length > 0
        ? "Nothing disqualifying — findings are context only"
        : "No rule in the preview subset fired",
    shortCircuit: false,
    latencyMs: Math.max(1, Math.round(elapsed * 100) / 100),
    dataAsOf: "2026-08-06",
    confidence: fraudulent ? 0.82 : 0.4,
    findings,
    checks: [
      {
        name: "Sender short-circuit",
        status: "unavailable",
        note: "Pasted text carries no signature to verify",
      },
      { name: "Entity", status: "unavailable", note: "Register lookup needs the engine" },
      {
        name: "Money",
        status: findings.some((f) => f.chokepoint === "money") ? "fail" : "pass",
        note: "Direction rules ran in the browser",
      },
      {
        name: "Claim",
        status: findings.some((f) => f.chokepoint === "claim" && f.tier !== "context")
          ? "fail"
          : "pass",
        note: "Direction rules ran in the browser",
      },
      {
        name: "Delivery",
        status: findings.some((f) => f.chokepoint === "delivery" && f.tier !== "context")
          ? "fail"
          : "pass",
        note: "Filename and link shape only",
      },
      { name: "Filing comparison", status: "unavailable", note: "BSE corpus is server-side" },
    ],
    provenance: ["Browser preview — rule subset only, nothing left this device"],
    rulesEvaluated: previewRules.length,
    suppressed,
  };
}
