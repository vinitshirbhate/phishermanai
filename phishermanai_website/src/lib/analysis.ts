/**
 * The verdict contract.
 *
 * These types mirror the shapes the Python engine returns from
 * `POST /api/v1/verify`, so swapping the recorded fixtures below for a live
 * call means changing where the object comes from, not what the UI reads.
 */

export type VerdictCode = "VERIFIED" | "NO_RISK_FOUND" | "TAMPERED" | "FRAUDULENT";

/** The four chokepoints, plus the two stages either side of them. */
export type Chokepoint = "sender" | "entity" | "money" | "claim" | "delivery" | "filing";

/**
 * Two tiers decide the verdict; `passing` and `context` never accuse on their
 * own. One disqualifying finding, or two weak ones alongside a request, is
 * what turns a message red.
 */
export type FindingTier = "disqualifying" | "weak" | "passing" | "context";

export interface FieldComparison {
  field: string;
  claimed: string;
  filed: string;
  source: string;
  asOf: string;
}

export interface Finding {
  id: string;
  chokepoint: Chokepoint;
  tier: FindingTier;
  /** 0–5. A rule with no declared action may never exceed 1. */
  severity: number;
  title: string;
  detail: string;
  comparison?: FieldComparison;
}

export interface CheckRun {
  name: string;
  status: "pass" | "fail" | "unavailable";
  note: string;
}

export interface AnalysisResult {
  verdict: VerdictCode;
  headline: string;
  /** True when aligned DKIM from a known domain answered before the checks ran. */
  shortCircuit: boolean;
  latencyMs: number;
  dataAsOf: string;
  /** 0–1. Below the gate, the engine returns NO_RISK_FOUND rather than guessing. */
  confidence: number;
  findings: Finding[];
  checks: CheckRun[];
  provenance: string[];
}

export interface AuthResult {
  spf: boolean;
  dkim: boolean;
  dmarc: boolean;
  /** DKIM alignment with the From: domain — the part DMARC alone does not give you. */
  aligned: boolean;
}

export interface DemoMessage {
  /** Matches the `?demo=` deep link used by the engine's own web UI. */
  id: string;
  label: string;
  blurb: string;
  channel: "email" | "whatsapp" | "screenshot";
  from: string;
  fromName: string;
  subject: string;
  received: string;
  body: string;
  attachments?: string[];
  auth: AuthResult;
  result: AnalysisResult;
}

export const verdictMeta: Record<
  VerdictCode,
  {
    label: string;
    dot: string;
    text: string;
    bg: string;
    border: string;
    ring: string;
    summary: string;
  }
> = {
  VERIFIED: {
    label: "Verified",
    dot: "bg-verdict-verified",
    text: "text-verdict-verified",
    bg: "bg-verdict-verified/10",
    border: "border-verdict-verified/30",
    ring: "ring-verdict-verified/25",
    summary: "Proven sender, or passing checks outnumber weak findings.",
  },
  NO_RISK_FOUND: {
    label: "No risk found",
    dot: "bg-verdict-quiet",
    text: "text-verdict-quiet",
    bg: "bg-verdict-quiet/10",
    border: "border-verdict-quiet/30",
    ring: "ring-verdict-quiet/25",
    summary: "Sender unconfirmed, but nothing asks for anything. Not an accusation.",
  },
  TAMPERED: {
    label: "Tampered",
    dot: "bg-verdict-tampered",
    text: "text-verdict-tampered",
    bg: "bg-verdict-tampered/10",
    border: "border-verdict-tampered/30",
    ring: "ring-verdict-tampered/25",
    summary: "Matches a real filing, but a field was altered.",
  },
  FRAUDULENT: {
    label: "Fraudulent",
    dot: "bg-verdict-fraud",
    text: "text-verdict-fraud",
    bg: "bg-verdict-fraud/10",
    border: "border-verdict-fraud/30",
    ring: "ring-verdict-fraud/25",
    summary: "One disqualifying finding, or two weak ones alongside a request.",
  },
};

export const chokepointMeta: Record<Chokepoint, { label: string; question: string }> = {
  sender: { label: "Sender", question: "Is the sender cryptographically proven?" },
  entity: { label: "Entity", question: "Does the named firm exist, and is it registered?" },
  money: { label: "Money", question: "Where is the money actually going?" },
  claim: { label: "Claim", question: "Is the promise one a registered firm may legally make?" },
  delivery: { label: "Delivery", question: "Does the channel match how this is really sent?" },
  filing: { label: "Filing", question: "Does it match what the company filed with the exchange?" },
};

/** The six stages a message passes through, used by the pipeline graphics. */
export const pipelineStages = [
  {
    id: "api",
    index: "01",
    title: "API",
    caption: "Three channels, one engine",
    detail:
      "Email, WhatsApp text and screenshots enter through the same endpoint. The channel changes how the message is read, never how it is judged.",
    kind: "linear" as const,
  },
  {
    id: "prep",
    index: "02",
    title: "Read & clean",
    caption: "Parse · strip · mask · unwrap",
    detail:
      "Hidden text is stripped, forwards are unwrapped, and demat IDs, PAN and phone numbers are masked before any rule sees the text.",
    kind: "linear" as const,
  },
  {
    id: "gate",
    index: "03",
    title: "Sender proven?",
    caption: "83% exit here in 10 ms",
    detail:
      "A valid, aligned DKIM signature from a known domain answers immediately. Most genuine mail never reaches the expensive checks.",
    kind: "gate" as const,
  },
  {
    id: "checks",
    index: "04",
    title: "Four checks",
    caption: "Entity · Money · Claim · Delivery",
    detail:
      "Four independent chokepoints run against real registers. Each returns findings tagged with its own meaning — risk, protective or context.",
    kind: "loop" as const,
  },
  {
    id: "filing",
    index: "05",
    title: "Compare to the filing",
    caption: "The differentiator",
    detail:
      "The document is matched to the corporate action the company actually filed with BSE, and every parsed field is compared value by value.",
    kind: "loop" as const,
  },
  {
    id: "decide",
    index: "06",
    title: "Weigh it up",
    caption: "Two tiers · safety rail · confidence gate",
    detail:
      "Findings are deduplicated, ordered worst-first and combined floor-only: a bad signal can drag trust down, a benign one can never lift it.",
    kind: "linear" as const,
  },
];

const BSE_SOURCE = "BSE corporate announcements";

export const demoMessages: DemoMessage[] = [
  {
    id: "genuine_01.eml",
    label: "Genuine dividend circular",
    blurb: "Aligned DKIM from a known registrar domain. Answered before the checks run.",
    channel: "email",
    fromName: "KFin Technologies Ltd",
    from: "corporate.actions@kfintech.com",
    subject: "Record date for interim dividend — Birla Corporation Limited",
    received: "09 Jul 2026, 11:04 IST",
    body: `Dear Shareholder,

This is to inform you that the Board of Directors of Birla Corporation Limited
has declared an interim dividend of Rs. 12.50 per equity share of face value
Rs. 10/- each for the financial year 2026-27.

The record date for determining eligibility is 24 July 2026. The dividend will
be credited to the bank account registered with your depository participant.

No action is required from you. Should your bank mandate need updating, please
do so through your depository participant directly.

Registrar & Transfer Agent
KFin Technologies Limited`,
    auth: { spf: true, dkim: true, dmarc: true, aligned: true },
    result: {
      verdict: "VERIFIED",
      headline: "Sender cryptographically proven — answered before the checks ran",
      shortCircuit: true,
      latencyMs: 10,
      dataAsOf: "2026-08-06",
      confidence: 0.99,
      provenance: ["DKIM public key, kfintech.com", "Curated domain map — 114 rows, DNS/MX verified"],
      findings: [
        {
          id: "dkim-aligned",
          chokepoint: "sender",
          tier: "passing",
          severity: 0,
          title: "Aligned DKIM from a known domain",
          detail:
            "The signature covers the From: header and validates against kfintech.com, which is a hand-verified registrar domain in the map. Alignment is what DMARC-pass alone does not tell you.",
        },
        {
          id: "no-request",
          chokepoint: "claim",
          tier: "passing",
          severity: 0,
          title: "No request of the reader",
          detail:
            "The message states an outcome and explicitly says no action is required. There is no payment, credential or click to act on.",
        },
      ],
      checks: [
        { name: "Sender short-circuit", status: "pass", note: "Aligned DKIM, known domain" },
        { name: "Entity", status: "pass", note: "KFin Technologies — SEBI-registered RTA" },
        { name: "Money", status: "pass", note: "No payment instrument present" },
        { name: "Claim", status: "pass", note: "No promise of return" },
        { name: "Delivery", status: "pass", note: "Channel matches issuer practice" },
      ],
    },
  },
  {
    id: "tampered_01.eml",
    label: "Tampered dividend circular",
    blurb:
      "A real circular from a real company with one number edited. Every authentication check passes.",
    channel: "email",
    fromName: "Birla Corporation Limited",
    from: "investors@birlacorporation.com",
    subject: "Interim dividend declared — Rs. 125.00 per share",
    received: "11 Jul 2026, 19:41 IST",
    body: `Dear Shareholder,

The Board of Directors has declared an interim dividend of Rs. 125.00 per
equity share for the financial year 2026-27.

To receive the enhanced payout, shareholders must confirm their bank mandate
through the shareholder portal before the record date of 24 July 2026.

Confirm mandate: https://birlacorp-shareholders.in/mandate

Investor Relations
Birla Corporation Limited`,
    auth: { spf: true, dkim: true, dmarc: true, aligned: false },
    result: {
      verdict: "TAMPERED",
      headline: "Matches a real BSE filing — with the dividend value altered",
      shortCircuit: false,
      latencyMs: 41,
      dataAsOf: "2026-08-06",
      confidence: 0.94,
      provenance: [
        `${BSE_SOURCE} — announcement dated 09 Jul 2026`,
        "Public Suffix List — registrable domain extraction",
      ],
      findings: [
        {
          id: "tamper-amount",
          chokepoint: "filing",
          tier: "disqualifying",
          severity: 5,
          title: "Dividend value does not match the filing",
          detail:
            "The document matched a real corporate action, so the comparison is field-by-field against the filed values. Python compares the parsed numbers; no model decides whether 125.00 equals 12.50.",
          comparison: {
            field: "Interim dividend per equity share",
            claimed: "₹125.00",
            filed: "₹12.50",
            source: BSE_SOURCE,
            asOf: "09 Jul 2026",
          },
        },
        {
          id: "delivery-domain",
          chokepoint: "delivery",
          tier: "weak",
          severity: 3,
          title: "Mandate link leaves the issuer's registrable domain",
          detail:
            "birlacorp-shareholders.in is a different registrable domain from birlacorporation.com. Lookalike letters are deliberately not folded — treating a homoglyph as equal would make the tool vouch for the impostor.",
        },
        {
          id: "record-date-ok",
          chokepoint: "filing",
          tier: "passing",
          severity: 0,
          title: "Record date matches the filing",
          detail:
            "24 July 2026 is exactly what was filed. Only one field was altered, which is why the document survives every authentication check.",
          comparison: {
            field: "Record date",
            claimed: "24 Jul 2026",
            filed: "24 Jul 2026",
            source: BSE_SOURCE,
            asOf: "09 Jul 2026",
          },
        },
      ],
      checks: [
        { name: "Sender short-circuit", status: "fail", note: "DKIM valid but not aligned" },
        { name: "Entity", status: "pass", note: "Birla Corporation — listed, scrip 500335" },
        { name: "Money", status: "pass", note: "No payment instrument present" },
        { name: "Claim", status: "pass", note: "Dividend is a lawful corporate action" },
        { name: "Delivery", status: "fail", note: "Off-domain mandate collection" },
        { name: "Filing comparison", status: "fail", note: "1 of 4 parsed fields differs" },
      ],
    },
  },
  {
    id: "fraud_02_guaranteed_returns.eml",
    label: "Guaranteed-returns pitch",
    blurb:
      "A real SEBI registration number, held by a different firm entirely. That mismatch is the detection.",
    channel: "whatsapp",
    fromName: "Alpha Wealth Circle",
    from: "+91 89xxx xxx41",
    subject: "VIP allocation closing today",
    received: "07 Aug 2026, 21:17 IST",
    body: `SEBI-registered advisory. Reg. No. INA000000383.

Our VIP group closed +40% last quarter and this month's allocation is
GUARANTEED 40% returns, capital fully protected.

Only 6 seats remain and the group closes tonight at 11 PM.

Pay the joining fee of Rs. 24,999 to investprofit99@ybl and send the
screenshot here. Share the OTP you receive so we can confirm the seat
immediately.`,
    attachments: ["Zerodha_Kite_Pro_Unlocked.apk"],
    auth: { spf: false, dkim: false, dmarc: false, aligned: false },
    result: {
      verdict: "FRAUDULENT",
      headline: "Registration collision — the number belongs to someone else",
      shortCircuit: false,
      latencyMs: 38,
      dataAsOf: "2026-08-06",
      confidence: 0.97,
      provenance: [
        "SEBI public register — IA and RA categories, 3,179 registrants",
        "NPCI @valid handle list",
        "Threat feeds — 819,572 domains, as of 2026-03-23",
      ],
      findings: [
        {
          id: "reg-collision",
          chokepoint: "entity",
          tier: "disqualifying",
          severity: 5,
          title: "Registration INA000000383 is registered to a different firm",
          detail:
            "Resolved against SEBI's public register: the number belongs to V R WEALTH ADVISORS PRIVATE LIMITED, not to this sender. A fraudster can rewrite the pitch endlessly; they cannot make a real number resolve to their own name.",
          comparison: {
            field: "Registration holder",
            claimed: "Alpha Wealth Circle",
            filed: "V R WEALTH ADVISORS PRIVATE LIMITED",
            source: "SEBI public register (IA)",
            asOf: "06 Aug 2026",
          },
        },
        {
          id: "guaranteed-return",
          chokepoint: "claim",
          tier: "disqualifying",
          severity: 5,
          title: "Guaranteed return with assured capital protection",
          detail:
            "No SEBI-registered intermediary may promise a return. The rule declares an entity, an action and a direction, so investor-awareness copy warning about this exact promise does not fire it.",
        },
        {
          id: "upi-outside-valid",
          chokepoint: "money",
          tier: "disqualifying",
          severity: 4,
          title: "Payment handle sits outside the @valid namespace",
          detail:
            "investprofit99@ybl is a consumer handle. Registered intermediaries collect only through the @valid namespace, which is restricted at the NPCI level and cannot be self-issued.",
          comparison: {
            field: "Collection handle",
            claimed: "investprofit99@ybl",
            filed: "@valid namespace required",
            source: "NPCI @valid registry",
            asOf: "06 Aug 2026",
          },
        },
        {
          id: "otp-outbound",
          chokepoint: "money",
          tier: "disqualifying",
          severity: 5,
          title: "Outbound OTP request",
          detail:
            "“Share the OTP you receive” asks the reader to send a credential outward. The same vocabulary pointed inward — “the system will send an OTP to your registered mobile” — is harmless and scores 0.",
        },
        {
          id: "apk-offer",
          chokepoint: "delivery",
          tier: "weak",
          severity: 3,
          title: "Installable app file delivered in chat",
          detail:
            "Zerodha_Kite_Pro_Unlocked.apk advertises a paid broker app unlocked for free and arrives over a chat channel. Judged on filename and delivery route, never on file contents.",
        },
        {
          id: "urgency",
          chokepoint: "claim",
          tier: "weak",
          severity: 2,
          title: "Manufactured deadline",
          detail:
            "“Closes tonight” and “6 seats remain” compress the decision window. On its own this is weak; it is reported as context beside the disqualifying findings.",
        },
      ],
      checks: [
        { name: "Sender short-circuit", status: "unavailable", note: "Chat channel — no DKIM to check" },
        { name: "Entity", status: "fail", note: "Registration collision" },
        { name: "Money", status: "fail", note: "Non-@valid handle · outbound OTP" },
        { name: "Claim", status: "fail", note: "Guaranteed return" },
        { name: "Delivery", status: "fail", note: "APK offer in chat" },
        { name: "Filing comparison", status: "unavailable", note: "No corporate action referenced" },
      ],
    },
  },
  {
    id: "edge_01_unregistered_but_real.eml",
    label: "Unregistered, but harmless",
    blurb:
      "Nothing proves the sender. Nothing asks for anything either. The honest answer is neither green nor red.",
    channel: "email",
    fromName: "Meridian Research Desk",
    from: "desk@meridian-research-notes.in",
    subject: "Weekly sector note — cement and building materials",
    received: "05 Aug 2026, 08:12 IST",
    body: `Good morning,

Our weekly note on the cement sector is attached. Capacity utilisation across
the eastern belt stayed near 71% through July, with pricing broadly flat
month on month.

This note is for information only. We do not offer advisory services and we
do not accept funds from readers.

Meridian Research Desk`,
    auth: { spf: true, dkim: false, dmarc: false, aligned: false },
    result: {
      verdict: "NO_RISK_FOUND",
      headline: "Sender unconfirmed — and nothing here asks for anything",
      shortCircuit: false,
      latencyMs: 36,
      dataAsOf: "2026-08-06",
      confidence: 0.58,
      provenance: [
        "SEBI public register — IA and RA categories, 3,179 registrants",
        "Curated domain map — 114 rows, DNS/MX verified",
      ],
      findings: [
        {
          id: "unknown-domain",
          chokepoint: "sender",
          tier: "context",
          severity: 1,
          title: "Domain is not in the verified map",
          detail:
            "meridian-research-notes.in is absent from the hand-curated map. Absence of coverage is reported as a coverage limit, never as evidence against the sender.",
        },
        {
          id: "no-registration",
          chokepoint: "entity",
          tier: "context",
          severity: 1,
          title: "No registration number to resolve",
          detail:
            "The note claims no advisory status, so there is no number to check. A missing credential only becomes a finding when the sender is acting in a role that requires one.",
        },
        {
          id: "no-ask",
          chokepoint: "money",
          tier: "passing",
          severity: 0,
          title: "No payment instrument, link or credential request",
          detail:
            "No UPI handle, bank account, IFSC, login page or OTP request appears anywhere in the message. This is what holds the verdict out of the red.",
        },
      ],
      checks: [
        { name: "Sender short-circuit", status: "fail", note: "No DKIM signature" },
        { name: "Entity", status: "unavailable", note: "No registration claimed" },
        { name: "Money", status: "pass", note: "No payment instrument present" },
        { name: "Claim", status: "pass", note: "No promise of return" },
        { name: "Delivery", status: "pass", note: "No installable or off-domain link" },
        { name: "Filing comparison", status: "unavailable", note: "No corporate action referenced" },
      ],
    },
  },
];

export function getDemoMessage(id: string | null | undefined): DemoMessage {
  if (!id) return demoMessages[0];
  return demoMessages.find((message) => message.id === id) ?? demoMessages[0];
}

export const findingTierMeta: Record<FindingTier, { label: string; className: string }> = {
  disqualifying: {
    label: "Disqualifying",
    className: "text-verdict-fraud border-verdict-fraud/35 bg-verdict-fraud/10",
  },
  weak: {
    label: "Weak",
    className: "text-verdict-tampered border-verdict-tampered/35 bg-verdict-tampered/10",
  },
  passing: {
    label: "Passing",
    className: "text-verdict-verified border-verdict-verified/35 bg-verdict-verified/10",
  },
  context: {
    label: "Context",
    className: "text-verdict-quiet border-verdict-quiet/35 bg-verdict-quiet/10",
  },
};
