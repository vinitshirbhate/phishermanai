import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AudioLines,
  Ban,
  Blocks,
  Braces,
  Building2,
  Fingerprint,
  Gauge,
  Globe,
  Landmark,
  Link2,
  Mail,
  MessageSquareWarning,
  Network,
  PackageOpen,
  Radar,
  ScrollText,
  ShieldCheck,
  Signature,
  Signpost,
  Users,
  Video,
} from "lucide-react";

export interface Stat {
  value: string;
  label: string;
  caption?: string;
}

export const headlineStats: Stat[] = [
  { value: "4", label: "Channels covered", caption: "email · voice · video · social · web" },
  { value: "0 / 155", label: "False positives", caption: "golden corpus, 35 adversarial" },
  { value: "10 ms", label: "Median verdict", caption: "83% of genuine mail" },
  { value: "377", label: "Tests passing", caption: "5 blocking CI gates" },
];

export const corpusStats: Stat[] = [
  { value: "8,434", label: "Real BSE filings", caption: "across 250 companies, 90 days" },
  { value: "10,367", label: "Entities", caption: "incl. 5,442 SEBI-registered intermediaries" },
  { value: "3,179", label: "IA + RA registrants", caption: "scraped from the public register" },
  { value: "819,572", label: "Blocklisted domains", caption: "three feeds, dated 2026-03-23" },
  { value: "377", label: "Tests passing", caption: "213 engine · 164 extension" },
  { value: "5", label: "CI gates", caption: "false accusations must stay at 0" },
];

/** The grayscale row under the hero — public sources, not customer logos. */
export const dataSources = [
  "BSE corporate announcements",
  "SEBI public register",
  "NSE",
  "NPCI @valid registry",
  "CDSL / NSDL scrip master",
  "Public Suffix List",
  "IFSC directory",
];

export interface Accreditation {
  icon: LucideIcon;
  label: string;
  caption: string;
}

export const accreditations: Accreditation[] = [
  {
    icon: Landmark,
    label: "SEBI PS-01",
    caption: "AI-driven detection of synthetic media and phishing in securities markets",
  },
  {
    icon: Ban,
    label: "Zero false accusations",
    caption: "Gate G-2 counts them on every eval run. Currently 0",
  },
  {
    icon: Network,
    label: "Runs offline",
    caption: "The email and web paths touch no network — pull the plug and they still answer",
  },
  {
    icon: Braces,
    label: "Evidence, not a score",
    caption: "Every verdict names the register it used and the date that register was read",
  },
];

/* ------------------------------------------------------------------ *
 * The threat landscape — what generative AI changed, per channel.
 * ------------------------------------------------------------------ */

export interface ThreatVector {
  icon: LucideIcon;
  channel: string;
  what: string;
  why: string;
}

export const threatVectors: ThreatVector[] = [
  {
    icon: Mail,
    channel: "Email and messaging",
    what: "LLMs write spear-phishing that matches a target's corporate context exactly, in unlimited variants.",
    why: "The cues people were taught to look for — bad grammar, generic salutations — are gone. Controlled tests of AI-crafted phishing show high false-negative rates across major commercial filters.",
  },
  {
    icon: AudioLines,
    channel: "Voice",
    what: "Cloned executive and regulator voices place calls that “confirm” a transfer or a fund allocation.",
    why: "Survey work puts the share of people who cannot distinguish a cloned voice from a real one at roughly 70%. The verification step itself becomes the attack.",
  },
  {
    icon: Video,
    channel: "Video",
    what: "Deepfaked CEOs, CIOs and market experts, including live participants on a video call.",
    why: "In a January 2024 case an employee joined a call with deepfaked colleagues and wired HK$200 million. Detectors trained on one generator are documented to fail on unseen ones.",
  },
  {
    icon: Globe,
    channel: "Social and web",
    what: "AI-generated posts, fake advisory pages and lookalike broker sites that move retail sentiment.",
    why: "First-generation investors meet the market on social platforms first. A doctored image can trigger a price move before anyone verifies it — and the liar's dividend means genuine notices get doubted too.",
  },
];

/* ------------------------------------------------------------------ *
 * The two halves the problem statement names.
 * ------------------------------------------------------------------ */

export interface Half {
  icon: LucideIcon;
  kicker: string;
  title: string;
  body: string;
  points: string[];
}

export const halves: Half[] = [
  {
    icon: Radar,
    kicker: "Half one",
    title: "Detection of malicious synthetic content",
    body: "Four channels, each with its own detector and its own measured performance. Nothing is collapsed into a single number, because a cloned voice and an altered circular are different claims with different consequences.",
    points: [
      "Intent-aware text rules that match direction, not vocabulary",
      "Synthetic-speech scoring over transcribed audio",
      "Frame-level deepfake analysis with the audio pipeline alongside it",
      "Coordination and market-anomaly correlation across stored chatter",
    ],
  },
  {
    icon: ShieldCheck,
    kicker: "Half two",
    title: "Verification of authentic communications",
    body: "The gap that compounds every attack above: no reliable way to confirm a notice really is from SEBI, an exchange, a listed company or a registered intermediary. A positive confirmation, not merely the absence of a flag.",
    points: [
      "Registry of official domains, handles and senders, with lookalike detection",
      "DKIM alignment against a hand-verified domain map",
      "Content checked against the filing the company actually made",
      "Digital-signature presence on documents that are required to carry one",
    ],
  },
];

/* ------------------------------------------------------------------ *
 * Channels — every one first-class, each with its own page.
 * ------------------------------------------------------------------ */

export interface Capability {
  title: string;
  body: string;
}

export interface Evidence {
  label: string;
  value: string;
  caption?: string;
}

export type Maturity = "measured" | "hosted" | "heuristic" | "partial";

export const maturityMeta: Record<Maturity, { label: string; className: string }> = {
  measured: {
    label: "Measured on a labelled set",
    className: "border-verdict-verified/35 bg-verdict-verified/10 text-verdict-verified",
  },
  hosted: {
    label: "Hosted detector — soft-fails to unavailable",
    className: "border-verdict-tampered/35 bg-verdict-tampered/10 text-verdict-tampered",
  },
  heuristic: {
    label: "Explainable heuristic, not a trained model",
    className: "border-verdict-quiet/35 bg-verdict-quiet/10 text-verdict-quiet",
  },
  partial: {
    label: "Partly shipped — see status",
    className: "border-verdict-tampered/35 bg-verdict-tampered/10 text-verdict-tampered",
  },
};

export interface Channel {
  id: "email" | "voice" | "video" | "social" | "web";
  index: string;
  href: string;
  icon: LucideIcon;
  name: string;
  navLabel: string;
  navDescription: string;
  tagline: string;
  /** One line for the equal-weight grid on the landing page. */
  summary: string;
  threatTitle: string;
  threatBody: string;
  detection: Capability[];
  authentication: Capability[];
  targetUsers: string[];
  channelsAddressed: string[];
  evidence: Evidence[];
  maturity: Maturity;
  maturityNote: string;
  diagram: "email" | "voice" | "video" | "social" | "web";
}

export const channels: Channel[] = [
  {
    id: "email",
    index: "01",
    href: "/product/email",
    icon: Mail,
    name: "Email and messaging",
    navLabel: "Email & messaging",
    navDescription: "LLM-written phishing, and circulars checked against the real filing.",
    tagline: "Where the money actually moves",
    summary:
      "Checks a message against the corporate action the company filed with the exchange — the only way to catch a real circular with one number edited.",
    threatTitle: "Perfect grammar, correct context, unlimited variants",
    threatBody:
      "An attacker feeds public data into a language model and gets spear-phishing that matches the target's corporate context exactly. The style cues investors were trained to spot are gone, and the same model produces a million non-identical copies, so signature matching has nothing to hold on to.",
    detection: [
      {
        title: "Four chokepoints on every message",
        body: "Entity, Money, Claim and Delivery run against real registers. Each returns findings tagged risk, protective or context, never merged into a single opaque score.",
      },
      {
        title: "Rules that match direction, not vocabulary",
        body: "“Share the OTP with me” and “an OTP will be sent to your registered mobile” contain the same words and mean opposite things. Every rule declares an entity, an action, a direction and its suppressors.",
      },
      {
        title: "Protected identifiers masked before any rule reads them",
        body: "Demat IDs, PAN and phone numbers are masked at parse time, so rules fire on the request rather than the value, and nothing sensitive is retained.",
      },
    ],
    authentication: [
      {
        title: "Aligned DKIM against a verified domain map",
        body: "A DMARC pass only says the mail came from the domain it claims. Alignment against a domain separately verified by DNS and MX is a different, stronger claim — and it answers 83% of genuine mail in 10 ms.",
      },
      {
        title: "Compared to the real filing",
        body: "The document is matched to the corporate action filed with BSE and every parsed field compared value by value. Python does the comparison; no model decides whether 125.00 equals 12.50.",
      },
    ],
    targetUsers: ["Retail and first-generation investors", "Registered intermediaries", "Registrars and transfer agents"],
    channelsAddressed: ["Email (full MIME)", "WhatsApp text", "Screenshots via OCR"],
    evidence: [
      { label: "Overall accuracy", value: "97.8%", caption: "46 fixtures, four classes" },
      { label: "Fraud recall", value: "95%", caption: "19 / 20" },
      { label: "Tamper recall", value: "70%", caption: "nothing deployed makes this check" },
      { label: "Tampered called genuine", value: "0", caption: "the number that must stay 0" },
      { label: "False positives", value: "0 / 155", caption: "golden corpus, 35 adversarial" },
      { label: "Median latency", value: "10 / 40 ms", caption: "short-circuit · full" },
    ],
    maturity: "measured",
    maturityNote:
      "The strongest-evidenced channel. Screenshots are the weak path at 7/10 against email's 16/16, and are reported separately rather than blended away.",
    diagram: "email",
  },
  {
    id: "voice",
    index: "02",
    href: "/product/voice",
    icon: AudioLines,
    name: "Voice",
    navLabel: "Voice",
    navDescription: "Cloned executive and regulator calls, scored for synthetic speech.",
    tagline: "When the verification step is the attack",
    summary:
      "Transcribes the call, scores it for synthetic speech, and checks the claimed source against the registry — while stating plainly that it cannot say whose voice was cloned.",
    threatTitle: "The callback that confirms the fraud",
    threatBody:
      "Cloned voices turn the standard control — “call them back to confirm” — into the delivery mechanism. Around 70% of people cannot tell a cloned voice from a real one, and a clone needs only seconds of public audio from an earnings call or an interview.",
    detection: [
      {
        title: "Transcribe, then score",
        body: "Whisper produces the transcript, which goes through the same direction-aware text rules as email. The audio itself is scored separately for synthetic-speech artefacts.",
      },
      {
        title: "Transcoded before upload",
        body: "Audio is converted to 16 kHz mono MP3 first, so a ten-minute clip lands near 3.6 MB and stays inside the 5 MB cap. Clips over the duration limit are rejected with a 413.",
      },
      {
        title: "No fallback to a bad model",
        body: "The previous local checkpoint scored genuine recordings as 100% spoof. It was removed rather than kept as a fallback: a confidently wrong answer is worse than an absent one.",
      },
    ],
    authentication: [
      {
        title: "Claimed source resolved against the registry",
        body: "A call claiming to be from a registered intermediary is checked against the register the same way an email is. The claim is verifiable even when the audio is not.",
      },
    ],
    targetUsers: ["Listed companies and their CXOs", "Registered intermediaries", "Retail investors receiving callbacks"],
    channelsAddressed: ["Uploaded call recordings", "Voice notes in chat", "Audio track of a video"],
    evidence: [
      { label: "Weight in fusion", value: "0.20", caption: "second only to text" },
      { label: "Speaker verification", value: "None", caption: "cannot say whose voice" },
      { label: "Upload cap", value: "5 MB", caption: "16 kHz mono, transcoded" },
      { label: "On failure", value: "unavailable", caption: "excluded, never scored 0" },
    ],
    maturity: "hosted",
    maturityNote:
      "Spoof detection is a hosted API, not a local model. Without a key or network the signal reports unavailable and fusion renormalises around it.",
    diagram: "voice",
  },
  {
    id: "video",
    index: "03",
    href: "/product/video",
    icon: Video,
    name: "Video",
    navLabel: "Video",
    navDescription: "Deepfaked executives, scored frame by frame with the audio alongside.",
    tagline: "The channel with the worst generalisation problem",
    summary:
      "Frame-level deepfake scoring with the full audio pipeline running alongside it, and an explicit statement that detectors trained on one generator fail on the next.",
    threatTitle: "A whole meeting of people who do not exist",
    threatBody:
      "In January 2024 an employee joined a video call with deepfaked likenesses of the CFO and colleagues and wired HK$200 million. Multimodal synthesis is what makes it work: a video call is corroborated by an email, which is corroborated by a voice note, and each channel vouches for the others.",
    detection: [
      {
        title: "Frames and audio, scored separately",
        body: "Visual artefact analysis runs over sampled frames while the whole audio pipeline runs on the track. Two independent readings on one file, reported separately.",
      },
      {
        title: "Fails soft, by design",
        body: "The detector is a free hosted Space. Cold starts and quota exhaustion are normal, so it degrades to unavailable and a verdict is still produced from the other channels.",
      },
      {
        title: "Duration capped, not silently truncated",
        body: "Uploads over the limit are rejected with a 413 rather than returned as an unscored low-risk verdict. A green band on content nothing examined is the worst failure this system could produce.",
      },
    ],
    authentication: [
      {
        title: "Provenance metadata, where it exists",
        body: "Content credentials are the direction the industry is moving in, and an official announcement that carries them can be confirmed positively. Almost no AI video carries them today, so their absence is not treated as evidence of anything.",
      },
    ],
    targetUsers: ["Listed companies and their CXOs", "Market infrastructure institutions", "Retail investors on video platforms"],
    channelsAddressed: ["Uploaded video files", "Recorded calls", "Clips circulating in chat"],
    evidence: [
      { label: "Weight in fusion", value: "0.20", caption: "equal to voice" },
      { label: "Generalisation", value: "Unproven", caption: "on generators outside the test set" },
      { label: "Availability", value: "Best-effort", caption: "free hosted Space" },
      { label: "Over the cap", value: "413", caption: "never an unscored pass" },
    ],
    maturity: "hosted",
    maturityNote:
      "The least reliable channel, and the one where published research is most consistent that detectors do not generalise. It is included because absence of a check is worse, and excluded from scoring whenever it cannot run.",
    diagram: "video",
  },
  {
    id: "social",
    index: "04",
    href: "/product/social",
    icon: MessageSquareWarning,
    name: "Social and coordination",
    navLabel: "Social & coordination",
    navDescription: "AI-generated campaigns, correlated against real market activity.",
    tagline: "Where first-generation investors meet the market",
    summary:
      "Clusters coordinated chatter by similarity and burst timing, then correlates it against abnormal price and volume on the tickers actually named.",
    threatTitle: "A thousand accounts saying the same thing at once",
    threatBody:
      "Generative models make it trivial to produce a thousand non-identical posts pushing one ticker. Retail and first-generation investors meet the market on these platforms first, and a coordinated push reads as organic enthusiasm rather than as a campaign.",
    detection: [
      {
        title: "Similarity plus burst timing",
        body: "TF-IDF similarity across stored chatter finds template reuse; burst timing finds the coordination. Both are inspectable — a regulator can be walked through why a cluster was flagged.",
      },
      {
        title: "Correlated against the market",
        body: "Tickers named in the content are checked for abnormal price and volume. A campaign that moves nothing and a campaign that lands are different findings.",
      },
      {
        title: "Metadata recovered from the URL",
        body: "Author and timestamp come out of the post URL itself — the handle sits in the path, and the status ID is a snowflake whose upper 41 bits are a millisecond timestamp.",
      },
    ],
    authentication: [
      {
        title: "Official accounts in the registry",
        body: "Verified handles for SEBI, the exchanges and registered intermediaries sit in the same registry as their domains, so a post claiming to be official can be confirmed rather than merely not flagged.",
      },
    ],
    targetUsers: ["Retail and first-generation investors", "Market infrastructure institutions", "SEBI surveillance"],
    channelsAddressed: ["Social posts and threads", "Broadcast chat groups", "Ingested news and forum content"],
    evidence: [
      { label: "Coordination weight", value: "0.10", caption: "in the fused score" },
      { label: "Market anomaly weight", value: "0.10", caption: "fires only with tickers found" },
      { label: "Method", value: "TF-IDF + burst", caption: "not a trained graph network" },
      { label: "Labelled bot data", value: "None held", caption: "which is why it is a heuristic" },
    ],
    maturity: "heuristic",
    maturityNote:
      "There is no labelled bot dataset here. A graph network trained on nothing would be less trustworthy than a method that can be explained to a regulator, so this stayed a heuristic on purpose.",
    diagram: "social",
  },
  {
    id: "web",
    index: "05",
    href: "/product/extension",
    icon: Globe,
    name: "Web and browser",
    navLabel: "Browser extension",
    navDescription: "Lookalike sites, fake advisers and APK offers, checked on-device.",
    tagline: "Before you click, install or pay",
    summary:
      "Four lanes watch the page you are on — links, advisers, chats and files — and resolve a claimed SEBI registration against the real register in about 0.1 ms, offline.",
    threatTitle: "A blocklist is always a day behind",
    threatBody:
      "Fraudsters rotate domains daily, so by the time one is on a list it has done its work. The durable question is not whether a domain is known-bad but whether the credential the law requires is present, and whether it belongs to whoever is showing it.",
    detection: [
      {
        title: "Registration collision",
        body: "A claimed number is resolved against 3,179 real registrants. Keep the number and it comes back held by someone else; remove it and the page breaks a disclosure rule mandatory since 1 May 2026.",
      },
      {
        title: "Link preflight",
        body: "Public Suffix List extraction so paytm.evil.co.in resolves to evil.co.in, plus homoglyph and punycode detection, IP literals in decimal, octal and hex, and redirect chains.",
      },
      {
        title: "Chat behaviour and file offers",
        body: "Reply-timing uniformity and template reuse are computed from timing and hashes without reading content. APK offers are judged on filename and delivery channel.",
      },
    ],
    authentication: [
      {
        title: "Lookalike letters are never folded",
        body: "Folding makes a Cyrillic nseindia.com compare equal to the real NSE domain, and the tool would vouch for the impostor. Missing an attack is bad; endorsing one is worse.",
      },
      {
        title: "@valid namespace for payments",
        body: "Registered intermediaries collect only through handles restricted at the NPCI level and impossible to self-issue. A consumer handle taking a fee is a rule breach, not a judgement call.",
      },
    ],
    targetUsers: ["Retail and first-generation investors", "Registered intermediaries distributing the tool"],
    channelsAddressed: ["Any web page", "WhatsApp Web", "Files offered in chat"],
    evidence: [
      { label: "MCC (URL model)", value: "0.6646", caption: "target ≥ 0.55 · CI 0.6597–0.6697" },
      { label: "Recall @ FPR ≤ 1%", value: "0.6112", caption: "target ≥ 0.85 — missed" },
      { label: "Link preflight", value: "17 / 17", caption: "0 false accusations" },
      { label: "Register lookup", value: "~0.1 ms", caption: "on-device, offline" },
    ],
    maturity: "partial",
    maturityNote:
      "Links, advisers and files run in a browser today. The WhatsApp lane is complete and tested but has no caller yet, and its DOM selectors have never run against live markup.",
    diagram: "web",
  },
];

export function getChannel(id: Channel["id"]): Channel {
  const channel = channels.find((item) => item.id === id);
  if (!channel) throw new Error(`Unknown channel: ${id}`);
  return channel;
}

/* ------------------------------------------------------------------ *
 * The authentication framework — half two, spanning every channel.
 * ------------------------------------------------------------------ */

export interface AuthLayer {
  icon: LucideIcon;
  name: string;
  answers: string;
  body: string;
  covers: string;
}

export const authLayers: AuthLayer[] = [
  {
    icon: Signature,
    name: "Sender authentication",
    answers: "Did this really come from the domain it claims?",
    body: "SPF, DKIM and DMARC are checked, and DKIM alignment is checked separately — because a pass on all three says nothing about whether the domain has any right to the name it trades under.",
    covers: "Email · messaging",
  },
  {
    icon: Link2,
    name: "Lookalike detection",
    answers: "Is this domain pretending to be one of the real ones?",
    body: "Registrable domains are extracted with the Public Suffix List and compared against the registry without folding homoglyphs, so a Cyrillic substitution can never compare equal to the genuine domain.",
    covers: "Email · web · social",
  },
  {
    icon: Fingerprint,
    name: "Registration resolution",
    answers: "Does this registration number belong to this sender?",
    body: "A claimed SEBI number is resolved against the public register. A collision — one number, two identities — is the detection, and no amount of rewriting the pitch removes it.",
    covers: "Web · email · social",
  },
  {
    icon: ScrollText,
    name: "Content verification",
    answers: "Does the message match what the company actually filed?",
    body: "The differentiator. A circular is matched to the corporate action filed with the exchange and every field compared. This is what catches a genuine document with one number altered.",
    covers: "Email · documents",
  },
  {
    icon: Signpost,
    name: "Signature presence",
    answers: "Is the mandated signature actually on this document?",
    body: "Presence is proved, validity is not — verifying a certificate chain against India's CCA trust store is out of scope. Absence on a document required to carry one is the actionable finding.",
    covers: "PDF circulars",
  },
  {
    icon: Landmark,
    name: "Official-channel registry",
    answers: "Is this an official channel at all?",
    body: "Domains, handles and senders for SEBI, the exchanges, listed companies and registered intermediaries, so a genuine communication is confirmed positively rather than merely not flagged.",
    covers: "Every channel",
  },
];

/* ------------------------------------------------------------------ *
 * Target users — the problem statement asks solutions to name them.
 * ------------------------------------------------------------------ */

export interface TargetUser {
  icon: LucideIcon;
  name: string;
  role: string;
  needs: string;
  surface: string;
}

export const targetUsers: TargetUser[] = [
  {
    icon: Users,
    name: "Retail and first-generation investors",
    role: "Primary beneficiary",
    needs:
      "A verdict in plain language with the reason attached — and a tool that stays quiet on the 155 genuine messages it has been measured against, because one false alarm on their real bank ends the relationship.",
    surface: "Browser extension · demo console",
  },
  {
    icon: Building2,
    name: "Registered intermediaries",
    role: "Target of impersonation, and a distribution channel",
    needs:
      "Early sight of advisories circulating in their name, and a tool they can hand to their own clients. Brokers, RIAs and mutual fund distributors are impersonated precisely because investors already trust them.",
    surface: "Broker dashboard · extension distribution",
  },
  {
    icon: Network,
    name: "Market infrastructure institutions",
    role: "Holders of the rails",
    needs:
      "Exchanges and depositories already hold verified investor contact channels and the filings themselves. In a deployed version they would publish to the registry at issuance, and verification would be instant rather than best-effort with a scraping lag.",
    surface: "Registry publishing · feed ingestion",
  },
  {
    icon: Landmark,
    name: "SEBI",
    role: "Anchor stakeholder for the authentication half",
    needs:
      "A cross-platform rollup of most-impersonated issuers with every row carrying its source and date, and a framework the regulator itself could own — signed circulars and a verified-sender registry are theirs to mandate.",
    surface: "Regulator dashboard · registry standard",
  },
];

/* ------------------------------------------------------------------ *
 * Mechanics shared across channels.
 * ------------------------------------------------------------------ */

export interface Lane {
  icon: LucideIcon;
  name: string;
  path: string;
  question: string;
  how: string;
}

export const lanes: Lane[] = [
  {
    icon: Link2,
    name: "Links",
    path: "preflight/",
    question: "Is this domain really who it claims?",
    how: "Public Suffix List, so paytm.evil.co.in resolves to evil.co.in. Homoglyph and punycode detection. IP literals in decimal, octal and hex. Redirect chains.",
  },
  {
    icon: Fingerprint,
    name: "Advisors",
    path: "securities_identity/",
    question: "Is that SEBI number real, and whose is it?",
    how: "3,179 real registrants from SEBI's public register, IA and RA categories. The number pattern is derived from the data, with a load-time assertion that it matches every row.",
  },
  {
    icon: MessageSquareWarning,
    name: "Chats",
    path: "whatsapp/",
    question: "Does this chat behave like a scam?",
    how: "Reply-timing uniformity, escalating money asks and template reuse across groups — computed from timing and hashes, without reading the content.",
  },
  {
    icon: PackageOpen,
    name: "Files",
    path: "shared/apk_check",
    question: "Should you install that APK?",
    how: "Filename plus delivery channel. Spotify (Premium) Mod2.apk is an app file sent in chat advertising a paid app unlocked free.",
  },
];

export interface Chokepoint {
  icon: LucideIcon;
  name: string;
  question: string;
  detail: string;
  register: string;
}

export const chokepoints: Chokepoint[] = [
  {
    icon: Fingerprint,
    name: "Entity",
    question: "Does the named firm exist, and does the number belong to it?",
    detail:
      "A claimed registration is resolved against the real register. Keeping a number gets caught as a collision; removing it breaks a disclosure rule mandatory since 1 May 2026.",
    register: "SEBI public register · 5,442 intermediaries",
  },
  {
    icon: Landmark,
    name: "Money",
    question: "Where is the money actually going?",
    detail:
      "UPI handles, bank accounts and IFSC codes are extracted and checked against the namespaces registered intermediaries are restricted to. Identifiers are masked before any rule reads them.",
    register: "NPCI @valid registry · IFSC directory",
  },
  {
    icon: ScrollText,
    name: "Claim",
    question: "Is this a promise a registered firm may legally make?",
    detail:
      "Rules match direction, not vocabulary. Every rule declares an entity, an action, a direction and suppressors, so investor-awareness copy about a scam never reads as the scam.",
    register: "Hand-curated rule table",
  },
  {
    icon: Radar,
    name: "Delivery",
    question: "Does the channel match how this is really sent?",
    detail:
      "Off-domain mandate collection, installable attachments and links whose registrable domain differs from the issuer's are all delivery findings, independent of what the text says.",
    register: "Curated domain map · 114 DNS/MX-verified rows",
  },
];

export interface Signal {
  icon: LucideIcon;
  name: string;
  weight: number;
  channel: string;
  what: string;
  limitation: string;
}

export const signals: Signal[] = [
  {
    icon: ScrollText,
    name: "text_phishing",
    weight: 0.25,
    channel: "Email · social",
    what: "Classifier score over the message text — the core signal, and the one everything else is weighed against.",
    limitation: "Requires the classifier service to be reachable.",
  },
  {
    icon: AudioLines,
    name: "voice_spoof",
    weight: 0.2,
    channel: "Voice",
    what: "Synthetic-speech detection over transcoded 16 kHz mono audio, after Whisper transcription.",
    limitation:
      "Hosted API. Without a key or network the signal reports unavailable — there is deliberately no fallback to the uncalibrated local checkpoint.",
  },
  {
    icon: Video,
    name: "video_deepfake",
    weight: 0.2,
    channel: "Video",
    what: "Frame-level deepfake scoring, with the whole audio pipeline running alongside it.",
    limitation:
      "A free hosted Space. Cold starts and quota exhaustion are normal; it soft-fails so a verdict still comes from the other channels.",
  },
  {
    icon: ShieldCheck,
    name: "source_untrusted",
    weight: 0.15,
    channel: "Every channel",
    what: "Registry lookup with lookalike-domain detection, so a genuine circular can be positively confirmed rather than merely not flagged.",
    limitation: "Registry-verified and digitally signed content is capped at Low.",
  },
  {
    icon: Activity,
    name: "coordination",
    weight: 0.1,
    channel: "Social",
    what: "Campaign analysis across stored chatter — TF-IDF similarity combined with burst timing.",
    limitation:
      "A heuristic, not a trained graph network. There is no labelled bot dataset here, and one trained on nothing would be less trustworthy than a method you can explain to a regulator.",
  },
  {
    icon: Gauge,
    name: "market_anomaly",
    weight: 0.1,
    channel: "Social · market",
    what: "Abnormal price and volume activity on tickers named in the content.",
    limitation:
      "Needs entity extraction to find tickers first; with none identified, the signal never fires.",
  },
];

export interface Gate {
  icon: LucideIcon;
  name: string;
  what: string;
}

export const gates: Gate[] = [
  {
    icon: Ban,
    name: "G-2 — false accusations",
    what: "Counted on every eval run. Target 0. Currently 0. The number is regenerated by script, never typed by hand.",
  },
  {
    icon: MessageSquareWarning,
    name: "Blocked claims",
    what: '"safe", "verified safe", "guaranteed protection" and "this is a deepfake" cannot appear in user-facing text. The build fails if they do.',
  },
  {
    icon: Blocks,
    name: "Parity",
    what: "The JavaScript and Python feature implementations must agree to ±0.02, or CI fails.",
  },
  {
    icon: Network,
    name: "Reachability",
    what: "A module that is built and never loaded fails the suite. It has caught real dead code twice.",
  },
  {
    icon: Signature,
    name: "Provenance",
    what: "Every answer names its sources and their dates. A clean link does not say “Safe ✓” — it says what was checked and what a check that recent cannot see.",
  },
];

export interface MetricRow {
  metric: string;
  result: string;
  target?: string;
  pass?: boolean;
  note?: string;
}

export const engineMetrics: MetricRow[] = [
  { metric: "Overall accuracy", result: "97.8%", note: "46 fixtures, four classes" },
  { metric: "Fraud recall", result: "95%", note: "19 / 20" },
  {
    metric: "Tamper detection recall",
    result: "70%",
    note: "the headline — nothing deployed does this check",
  },
  { metric: "Tampered documents called genuine", result: "0", note: "the number that must stay zero" },
  { metric: "False positives, golden corpus", result: "0 / 155", note: "incl. 35 adversarial" },
  { metric: "Short-circuit rate", result: "83%", note: "of genuine mail" },
  {
    metric: "Median latency",
    result: "10 ms / 40 ms",
    note: "short-circuit · full · ~3 s screenshots",
  },
];

export const extensionMetrics: MetricRow[] = [
  { metric: "MCC (URL model)", result: "0.6646", target: "≥ 0.55", pass: true, note: "CI 0.6597–0.6697" },
  { metric: "Recall @ FPR ≤ 1%", result: "0.6112", target: "≥ 0.85", pass: false },
  { metric: "Brier score", result: "0.1317", target: "≤ 0.12", pass: false },
  { metric: "G-2 false accusations", result: "0", target: "0", pass: true },
];

export interface AblationRow {
  configuration: string;
  fpRate: string;
  fraudRecall: string;
  shipped?: boolean;
}

export const ablation: AblationRow[] = [
  { configuration: "Both enabled (shipped)", fpRate: "0.0%", fraudRecall: "95.0%", shipped: true },
  { configuration: "Awareness suppression off", fpRate: "1.9%", fraudRecall: "95.0%" },
  { configuration: "Short-circuit off", fpRate: "0.0%", fraudRecall: "95.0%" },
  { configuration: "Both off — rules alone", fpRate: "3.9%", fraudRecall: "95.0%" },
];

export type LimitationScope = "Email" | "Voice" | "Video" | "Social" | "Web" | "Authentication";

export interface Limitation {
  title: string;
  body: string;
  scope: LimitationScope;
}

export const limitations: Limitation[] = [
  {
    scope: "Email",
    title: "The filings cross-check covers listed-company corporate actions only",
    body: "Dividends, splits, bonuses and buybacks are what the comparison reaches. Everything wider is carried by the four chokepoints, which do not need a filing to exist.",
  },
  {
    scope: "Email",
    title: "The corpora are real-shaped but synthetic",
    body: "Fixtures are built from the structure of genuine notices, not sampled from real inboxes. The filings they are compared against are real.",
  },
  {
    scope: "Email",
    title: "Screenshots are weaker than email",
    body: "7 / 10 against 16 / 16. OCR on WhatsApp-compressed text runs words together, and an unreadable field can never produce a tamper finding.",
  },
  {
    scope: "Email",
    title: "Confidence constants are hand-tuned",
    body: "Fitted to this fixture set rather than to labelled data. They are the part most likely to move with real deployment traffic.",
  },
  {
    scope: "Voice",
    title: "No speaker verification",
    body: "The system can say audio carries synthetic artefacts, but not whose voice was cloned. Restoring the speaker-embedding model is what would bring back the cloned-official verdict, which was removed rather than left firing on a check that no longer existed.",
  },
  {
    scope: "Voice",
    title: "Spoof detection is a hosted API, not a local model",
    body: "It needs a key and network access. Without either, the signal reports unavailable and fusion renormalises. There is deliberately no fallback to the previous local checkpoint, which scored genuine recordings as 100% spoof.",
  },
  {
    scope: "Video",
    title: "Detectors do not generalise to unseen generators",
    body: "This is the consistent finding across published surveys, not a quirk of this implementation. It is why the video signal is weighted alongside others rather than trusted alone, and why it is excluded entirely when it cannot run.",
  },
  {
    scope: "Video",
    title: "The video detector is a free hosted Space",
    body: "Cold starts, quota exhaustion and downtime are normal. It soft-fails to unavailable so a verdict is still produced from the other channels.",
  },
  {
    scope: "Social",
    title: "The coordination engine is a heuristic",
    body: "TF-IDF similarity plus burst timing, not a trained graph network. There is no labelled bot dataset here, and a model trained on nothing would be less explainable to a regulator than a method you can walk through.",
  },
  {
    scope: "Social",
    title: "Market correlation needs entity extraction to fire",
    body: "With no tickers identified in the content, the market signal never runs and is excluded from the fused score rather than counted as a zero.",
  },
  {
    scope: "Web",
    title: "Register coverage is IA and RA only",
    body: "A broker number (INZ…) returns “could not be checked — outside this snapshot's categories”, never “invalid”. Absence of coverage is never reported as evidence of fraud.",
  },
  {
    scope: "Web",
    title: "The WhatsApp lane is built and tested, but not yet running in a browser",
    body: "Its modules are complete, but adapter.start() has no caller, so no badge appears on a live WhatsApp page. Chat context is not fed into the SEBI-disclosure rule.",
  },
  {
    scope: "Web",
    title: "WhatsApp and Gmail DOM selectors have never run against live markup",
    body: "Fixtures we write would match selectors we wrote and prove nothing. This needs human-captured snapshots.",
  },
  {
    scope: "Authentication",
    title: "The domain map is hand-curated and does not yet scale",
    body: "114 rows, DNS and MX verified. Entries are never auto-inserted, because a wrong one is a permanent false VERIFIED — the most expensive error the system can make.",
  },
  {
    scope: "Authentication",
    title: "Signature checking proves presence, not validity",
    body: "Verifying the certificate chain against India's CCA trust store is out of scope. Absence on a document claiming to be a mandated-signature circular is the actionable finding.",
  },
  {
    scope: "Authentication",
    title: "Institutional integration is a roadmap item, not a built feature",
    body: "We scrape because we have no relationship with the exchanges. In a deployed version they would publish to the registry at issuance and verification would be instant rather than best-effort with a lag.",
  },
  {
    scope: "Authentication",
    title: "Threat feeds are dated 2026-03-23",
    body: "A domain registered after that date would not appear. The UI shows the date rather than hiding it.",
  },
];
