# requirement.md

# Phisherman AI — Securities Market Edition
## Requirements Specification

**Problem statement addressed:** AI-Driven Detection of Synthetic Media and Phishing Attacks in Securities Markets
**Baseline system:** Phisherman AI Browser Guard v6.2 (Chrome MV3 + FastAPI, ~7,000 LOC, working)
**Target release:** v7.0
**Document version:** 1.0 — 1 August 2026
**Status:** For build

---

## 1. Scope and Solution Thesis

### 1.1 The two halves of the problem

The problem statement has two halves, and they are usually treated as separate products. They are not.

| Half | Question | Failure mode today |
|---|---|---|
| **Detection** | Is this content synthetic or malicious? | Detectors chase a target the adversary can regenerate for free |
| **Authentication** | Is this communication genuinely from who it claims? | No mechanism exists for an investor to check |

**Thesis of this specification:** detection alone is a losing arms race, and the evidence is unambiguous. In-the-wild deepfake benchmarks put fine-tuned open-source detectors at 61–69% accuracy against ~82% for the leading commercial detector; audio deepfake detectors show error rates rising 200–1000% moving from laboratory corpora to real-world samples; controlled human-subject studies now put fully-automated AI phishing at parity with human experts (54% click-through against a 12% control). Every content heuristic that ever worked — bad grammar, generic salutations, template reuse — was eliminated first by generative AI.

Authentication is the more stable ground, and India's securities regulator has, in the last ten months, created **four machine-checkable identity anchors that did not exist before**:

1. **`@valid` UPI namespace** (live 1 Oct 2025) — NPCI-issued handles for registered intermediaries, with category suffixes, plus **SEBI Check** for verifying a UPI ID or bank account + IFSC.
2. **Mandatory registration disclosure** (SEBI Circular HO/(79)2026-MIRSD-PODMMC, 26 Feb 2026) — **since 1 May 2026**, every SEBI-regulated entity and agent must display its registered name and registration number on social-media home pages *and at the start of every securities-market content item*.
3. **Verified App Label** (25 Mar 2026) — verified badge for registered intermediaries' apps on Google Play.
4. **SGI labelling and provenance metadata** (IT Amendment Rules 2026, in force 20 Feb 2026) — synthetically generated information must carry prominent labels and persistent provenance metadata.

This flips the logic from **blocklist reasoning** (look for signs of badness, which adversaries optimise against) to **allowlist reasoning** (look for the absence of a credential the law now requires). A registration number cannot be paraphrased away. That is the architectural insight this specification is built on.

### 1.2 System purpose

> Phisherman AI scores every page, message, media object and payment surface a user encounters, verifies it against the identity anchors that legitimate securities-market participants are now required to carry, and — when something is wrong — produces a signed evidence packet and routes the user to the correct official channel. All of it works with the network disabled.

### 1.3 In scope

- Detection across **five surfaces**: web pages, messaging (WhatsApp Web / Telegram Web), email, voice notes and calls (via companion), video and image media.
- Authentication across **five anchor types**: registration identity, payment namespace, application integrity, sender/domain authenticity, content provenance.
- **Three user tiers**: retail investor (individual), intermediary (broker/RA/IA/AMC compliance), market infrastructure institution (exchange/depository surveillance).
- Evidence generation and routing to Indian official rails.

### 1.4 Out of scope

| Excluded | Rationale |
|---|---|
| Autonomous engagement with attackers (honeypots, LLM auto-reply, RL deception) | Contradicts the system's own guardrail model (`side_effects: false`, "No outbound send"); difficult to defend under DPDPA proportionality and SEBI Reg 16C liability. Parked as roadmap. |
| Blockchain / IPFS evidence anchoring | ECDSA-signed local export already delivers tamper-evidence without a dependency, a wallet, or a cost. |
| Binary "this is a deepfake" verdicts | Unsupportable at current detector accuracy. The system reports provenance states and content signals instead. |
| Docker, Kubernetes, message queues, microservices, hosted database | Explicit constraint. One Python process, one browser extension, SQLite. |
| Native call/SMS interception without a companion app | Already listed in the system's own `blocked_claims`. |
| Live carrier signals (SIM-swap, number verification) | Requires telecom consent policy — listed in the system's own `release_blockers`. |
| Multi-tenant SaaS, user accounts, JWT auth | The consumer product is single-user and local. The organisational console (FR-C7) is a separate, optional local deployment. |

---

## 2. Analysis of the Existing System

### 2.1 What exists and works

| Component | Detail | Assessment |
|---|---|---|
| **Chrome MV3 extension** | `background.js` (1,049 LOC), `content_script.js` (1,056 LOC), sidepanel (499 LOC), options. No bundler, no build step. | Solid. Loads unpacked in seconds. |
| **Four-layer fallback chain** | domain cache (24h TTL) → Ollama phi4-mini via FastAPI :8799 → cloud API → 18-rule offline gate | **The strongest asset.** Graceful degradation is genuinely rare and directly serves the users most exposed to investment fraud, who are typically on the worst networks. |
| **FastAPI backend** | `:8799`, 20 endpoints across analyze / fact-check / scamgate / gate / stats / history. Only 3 dependencies. | Clean. Additive extension is straightforward. |
| **Detection engines** | `trust_engine` (419), `scamgate` (863, Ollama lane), `threat_feeds` (486), `security_gate` (484), `fact_checker` (316), `domain_intel` (291), `scam_detector` (272), `manipulation_detector` (186) | Well-separated. Weighted-signal aggregation with 32 risk weights. |
| **Signed capability contracts** | ECDSA P-256/SHA-256 via `contract_security.py`. 8 modules and 6 agents declaring tier, capabilities, data classes, network hosts, guardrails-as-data. `trusted_signers` + `revocations`. | **Genuinely unusual and directly maps to SEBI Reg 16C**, which places sole liability for AI output on the deploying entity. |
| **Surface hooks** | Page load, link hover, form submit, WhatsApp Web live message scan, Telegram Web forwarded-message scan, right-click, side panel | Right set of interception points. |
| **India threat corpus** | `scam_patterns.yaml`, `india_scam_patterns.json`, `upi_fraud_patterns.json`, `scam_signals.json`, `risk_weights.json`, govt whitelists | Good coverage of digital arrest, UPI, OTP, lottery, loan, courier, task scams. |
| **Recovery rails** | Chakshu/Sanchar Saathi, NCRP/1930, I4C suspect repository, NPCI guidance, with correct routing on `lost_money` | Completes `scan → warn → evidence → rail`. Almost nobody else goes past "warn". |
| **Design laws** (`docs/delta_pack_v2`, `v3`) | "Provenance, not deepfake." "Missing credentials are not proof of deception." "Do not collapse verified channel / verified sender / verified content / safe interaction." "No certainty theatre. No hidden reporting." | Independently correct reads of the field. Preserve verbatim. |
| **Honesty constraints** | `extension_policy.json` declares `blocked_claims` (no "safe", no "guaranteed protection", no "government affiliated") and `release_blockers` | Rare discipline. Treated as binding in this specification. |

### 2.2 Gaps this specification closes

| # | Gap | Evidence | Severity |
|---|---|---|---|
| **L1** | **No securities layer.** Whole-tree grep finds one generic `investment_scam` category, a `stock tips` keyword, and a single regex matching `(rbi\|reserve bank\|sebi)\s*(notice\|order\|directive\|warning)`. | Codebase | **Critical** — this is the problem statement's core domain |
| **L2** | **No authentication capability at all.** Nothing validates a registration number, a `@valid` UPI handle, an app label, a sender domain, or a C2PA manifest. `trust_playbooks.py` references C2PA as a *plan*; no implementation exists. | Codebase | **Critical** — this is half the problem statement |
| **L3** | **No ML model.** Detection is regex + LLM. The LLM lane is invoked on every cache miss. | `requirements.txt` has no ML dependency | High |
| **L4** | **No evaluation.** No test set, no confusion matrix, no latency measurement, no metric anywhere. `tests/test_backend.py` is API contract testing. | Codebase | **Critical** — the problem statement asks for "clear evidence of detection or authentication performance" |
| **L5** | **No email channel.** No SMTP, IMAP, MIME parsing, or webmail DOM hook. | Codebase | High |
| **L6** | **No voice or video channel.** No audio pipeline, no transcription, no image/video handling. | Codebase | High |
| **L7** | **Single-user only.** No path for an intermediary compliance team or an exchange surveillance desk. | Codebase | Medium |
| **L8** | **No cross-channel correlation.** Each scan is independent; a campaign spanning email → WhatsApp → call → app is seen as four unrelated events. | Codebase | Medium |
| **L9** | Demo fixtures are transparently synthetic (`9876543210`, `9090909090`, `8080808080`) and not labelled as such. | `india_scam_patterns.json` | Medium (credibility) |
| **L10** | `backend/app.py` (:8898) cannot start — imports unvendored `risk_engine`. All six agents in `agent_registry.json` point at that dead port. | `context.md` admits this | Medium |
| **L11** | README states 10 local-gate rules; there are 18. | README vs `background.js` | Low (credibility) |
| **L12** | ~120 MB of blocklist feeds shipped alongside "we are not a blocklist" positioning. | `backend/data/feeds/` | Low (framing) |

---

## 3. User Personas

### P1 — Retail investor ("Ravi")
- **Profile:** 29, Nagpur, 18 months in the market, trades on a phone, member of four WhatsApp "research" groups.
- **Job to be done:** decide, in seconds, whether the person asking for money is who they claim to be.
- **Pain:** has seen three weeks of screenshots showing profits; the group feels like a community; the certificate looks official.
- **Needs:** F-A1, F-A5, F-B1, F-B2, F-C1, F-C3
- **Success:** stops before the first transfer, or before the escalation transfer.

### P2 — First-generation investor ("Sunita")
- **Profile:** 42, Guwahati, one SIP, English is her third language, patchy 4G.
- **Job:** understand a warning well enough to act on it.
- **Pain:** generic warnings ("this may be a scam") do not survive against three weeks of manufactured trust. She already checks — 96% of Indian adults take at least one verification step — but the heuristics she was taught are the ones AI eliminated first.
- **Needs:** NFR-7 (language, reading level), NFR-8 (trust UX), F-C2 (specific reason codes), F-A5 offline path
- **Success:** the warning names the *specific* mismatch, in a language she reads, without a network connection.

### P3 — Broker relationship manager ("Imran")
- **Profile:** front-office at a mid-size broker; clients forward him suspicious messages daily.
- **Job:** triage client-forwarded content quickly and correctly.
- **Needs:** F-A1, F-A4, F-C4 (evidence packet), F-C7 (org console)
- **Success:** a client's forwarded message returns a verdict with a citable SEBI advisory reference in under a minute.

### P4 — Compliance officer ("Mehta")
- **Profile:** 3-person compliance team at a SEBI-registered intermediary; CSCRF audit pending; Reg 16C makes his firm solely liable for the output of any AI tool it deploys.
- **Job:** detect and escalate impersonation *of his own firm*.
- **Pain:** finds out about impersonation when a client complains, not before.
- **Needs:** F-B1 collision detection, F-C6 impersonation alert, F-C7 org console, F-D (auditable AI), NFR-5 (CSCRF, Reg 16C)
- **Success:** an alert naming the impersonating handles, with content hashes and timestamps, in a form he can attach to a takedown request.

### P5 — MII surveillance analyst ("Priya")
- **Profile:** exchange or depository; watches for market-integrity events including coordinated retail manipulation.
- **Job:** spot a campaign, not a message.
- **Needs:** F-A7 (campaign correlation), F-C7, F-E (integration adapters)
- **Success:** deduplicated campaign clusters with lifecycle and resurfacing signals, exportable.

### P6 — Regulator analyst (secondary)
- **Profile:** reviews escalations and takedown requests at scale — SEBI has escalated over 1.3 lakh instances of misleading investment content for takedown.
- **Needs:** structured, deduplicated, provenance-carrying case packets.
- **Success:** case packets that arrive complete and do not need enrichment.

---

## 4. Target Channels

| # | Channel | Attack vector in securities context | Detection signals | Authentication anchor | Priority |
|---|---|---|---|---|---|
| **CH1** | **Web / app** | Cloned broker sites, fake trading platforms, private-link "VIP" apps, forged SEBI document pages | DOM structure, URL lexical, visual similarity, typosquat distance to registered intermediary names | Registration number, Verified App Label, domain whitelist | **P0** |
| **CH2** | **Messaging** (WhatsApp Web, Telegram Web) | "VIP trading groups", forged registration certificates, profit screenshots, unsolicited adds, WhatsApp Web session hijack ("Boss Scam") | Message text patterns, group-behaviour cues, image reuse via perceptual hash | Registration disclosure, `@valid` UPI, channel identity | **P0** |
| **CH3** | **Payment surface** | Collection into personal accounts outside the regulated perimeter; withdrawal traps ("tax", "processing fee") | UPI ID extraction, QR decode, account+IFSC extraction, amount-escalation pattern | **`@valid` namespace + SEBI Check** | **P0** |
| **CH4** | **Email** | LLM-crafted spear phishing, forged SEBI/exchange notices, fake STT demands, BEC against intermediaries | Header analysis, MIME structure, link extraction, LLM-style cues, attachment inspection | SPF/DKIM/DMARC alignment + official-domain registry | **P1** |
| **CH5** | **Voice** | Synthetic voice calls impersonating CEOs, CIOs, regulators; "digital arrest"; Boss Scam voice cloning | Local transcript → text engine; script pattern (authority + urgency + payment + secrecy) | Callback-only verification via official channel; **never a synthetic-voice verdict** | **P1** |
| **CH6** | **Video / image** | Deepfake CEO/CIO videos, fabricated exchange-official statements, forged certificates and letterheads | C2PA manifest inspection, SGI label presence, perceptual hash against known campaign assets, template/seal matching | **Content provenance (C2PA) + official-channel cross-check** | **P1** |
| **CH7** | **Social media** | Coordinated retail manipulation, unregistered advisory, finfluencer impersonation | Posting cadence, account age vs volume, near-duplicate templates across handles, engagement anomalies | **Registration disclosure mandatory since 1 May 2026** | **P1** |

---

## 5. Functional Requirements

Priority: **P0** = release blocker · **P1** = ship if capacity allows · **P2** = architected for, not built.

---

### 5.A Detection Requirements

---

#### F-A1 · Securities-aware text and message detection — **P0**

Extend `scam_patterns.yaml` with a `securities:` block covering typologies SEBI has itself published, each carrying a `source` field rendered in the UI so the user sees *why* and *on whose authority*.

| Pattern class | Weight | Cues |
|---|---|---|
| `fake_stt_notice` | 50 | "outstanding STT", "securities transaction tax due", SEBI letterhead markers + payment demand, claimed RBI coordination |
| `account_handling` | 45 | "account handling", "risk-free profit", "professional fund manager", profit-share %, minimum-capital demand |
| `fpi_institutional_lure` | 50 | "institutional trading account", "FPI route", "IPO allotment at discount", "block trade at cheap rate" — none of these products exist for resident retail |
| `vip_group_funnel` | 35 | unsolicited add + VIP/premium/W-number group naming + private app link |
| `withdrawal_trap` | 55 | withdrawal blocked behind "tax" / "processing fee" / "verification charge" / "margin top-up" |
| `fake_mf_redemption` | 40 | redemption routed off-platform, impersonated folio holder |
| `boss_scam` | 50 | CEO/MD impersonation + urgency + confidentiality + off-channel payment instruction |
| `forged_sebi_document` | 50 | SEBI seal/logo/letterhead markers + a registration claim that fails F-B1 |
| `guaranteed_return_claim` | 40 | "assured returns", "risk-free", "guaranteed profit" on securities content — prohibited claim, therefore a regulatory signal, not a stylistic one |

**Acceptance criteria**
- [ ] Each class has ≥ 3 regex variants, ≥ 5 keyword cues, ≥ 1 positive fixture, ≥ 1 near-miss negative fixture.
- [ ] Each class carries a `source` URL to the originating SEBI advisory, displayed in the sidepanel reason list.
- [ ] Hindi and Hinglish variants exist for the six highest-frequency classes.
- [ ] Adding the pack does not raise false-positive rate on the legitimate cohort above the NFR budget.
- [ ] Given a message matching `withdrawal_trap` on a page also matching `vip_group_funnel`, the combined verdict is HIGH and both reason codes render.

---

#### F-A2 · ML detection lane — **P0**

Insert a trained classifier between the domain cache and the LLM lane, deployed twice from one training run.

**Rationale, with evidence.** Benchmarking on 83,446 emails shows classical ML at 97–98% accuracy with 0.0001–0.0033 s inference and Bi-GRU at 98.77% (AUC 0.9987), against quantized small LLMs at 79–81% accuracy with 9,612–21,420 s. ML is roughly **1.38 million times faster and more accurate**. The current chain sends every cache miss to the slowest, least accurate lane first.

- **Layer 1.5a — in-extension.** Logistic Regression exported to `extension/models/lr_v1.json` as `{feature_names, means, scales, coefficients, intercept}`, scored by ~40 lines of JS in the service worker. Offline, zero dependencies.
- **Layer 1.5b — backend.** Gradient-boosted trees or Balanced Random Forest, joblib-serialised, loaded once at FastAPI startup.

**Confidence-band routing:** `p < 0.15` → allow · `p > 0.85` → warn · otherwise → escalate to LLM lane.

**Feature set — 24 features, single definition in `ml/features.py`:**

| Group | Features |
|---|---|
| Lexical (7) | `url_length`, `url_entropy`, `subdomain_count`, `param_count`, `has_ip_host`, `has_punycode`, `sensitive_keyword_count` |
| DOM structural (10) | `external_link_ratio`, `empty_links_ratio`, `suspicious_form_action`, `hidden_iframe_count`, `script_to_content_ratio`, `password_field_count`, `input_field_count`, `meta_refresh_present`, `external_resource_ratio`, `dom_nesting_depth` |
| Securities / India (7) | `upi_id_present`, `upi_outside_valid_namespace`, `registration_claim_present`, `registration_resolves`, `securities_keyword_density`, `typosquat_distance_to_intermediary`, `guaranteed_return_claim_present` |

**Acceptance criteria**
- [ ] `python -m ml.train` reads `datasets/`, writes `clf_v1.pkl` + `lr_v1.json`, prints metrics, exits 0.
- [ ] Layer 1.5a scores in < 10 ms in the service worker (measured and logged).
- [ ] Layer 1.5b p95 < 50 ms.
- [ ] **JS and Python scorers agree within ±0.02 on a 200-row parity fixture.** Silent scaler mismatch is the highest-probability defect in this build; this test is a gate, not a nicety.
- [ ] LLM invocation rate ≤ 25% of scans on the eval corpus.
- [ ] With the backend down, Layer 1.5a still runs; with Ollama down, the chain still returns a verdict.

---

#### F-A3 · Voice-note and call-audio lane — **P1**

User-initiated only. Right-click or drag a voice note → local transcription (`faster-whisper`, tiny/base, CPU) → transcript enters the **existing** text engine.

**Acceptance criteria**
- [ ] Audio never leaves the machine; the UI states this.
- [ ] 30-second Hindi/English note transcribes in ≤ 20 s on CPU.
- [ ] Output reports content signals (authority impersonation, urgency, payment instruction, secrecy demand, OTP solicitation) and `provenance_unverified`.
- [ ] **The system never asserts that a voice is synthetic.** Given audio-detector out-of-domain degradation of 200–1000%, that claim is unsupportable and is added to `blocked_claims`.
- [ ] If `faster-whisper` is absent, the feature reports "unavailable" and nothing else breaks.

---

#### F-A4 · Video and image assessment lane — **P1**

**Acceptance criteria**
- [ ] C2PA/Content Credentials manifest inspected where present; four states emitted per `schemas/provenance_assessment.json`.
- [ ] SGI labels required under the IT Amendment Rules 2026 are read and surfaced when present; never stripped.
- [ ] Perceptual hash (pHash/dHash) computed and matched against a local campaign-asset store — reused "profit screenshots", certificate templates, seals and logos are the single most reliable operational tell, because producing genuinely novel forgeries at scale is expensive.
- [ ] Where a media-forensics score is shown at all, it is shown as a **range with a confidence label**, never a binary, and never as the deciding signal.
- [ ] The words "deepfake", "fake" and "AI-generated" never appear as a verdict in the UI.

---

#### F-A5 · Web and application surface detection — **P0** (extends existing)

**Acceptance criteria**
- [ ] Typosquat distance computed against the bundled registered-intermediary name list (edit distance + homoglyph + phonetic).
- [ ] Domain age and certificate age retrieved where available; absence degrades gracefully.
- [ ] Android app listings: Verified App Label presence checked; sideload-encouraging language flagged.
- [ ] Private-link platforms displaying a portfolio balance with no corresponding registration disclosure raise `unregistered_trading_surface`.

---

#### F-A6 · Payment-surface guard — **P0**

**Acceptance criteria**
- [ ] Given a UPI ID outside `@valid` on a page scoring < 50 trust, when the user focuses the payment field, an interstitial appears with a "Verify on SEBI Check" deep link.
- [ ] Given a `@valid` handle whose category suffix contradicts the claimed entity type, flag `category_mismatch`.
- [ ] QR codes in page or message content are decoded and the embedded UPI string evaluated.
- [ ] Escalating-amount sequences to the same unverified payee within a session raise `escalation_ladder`.
- [ ] The interstitial is always dismissible. **The system never blocks a payment.**
- [ ] No payment data is transmitted anywhere.

---

#### F-A7 · Cross-channel campaign correlation — **P1**

Local-only correlation of independently observed events into campaign objects.

**Acceptance criteria**
- [ ] Entities linked: registration number, UPI ID, phone, domain, handle, group name, image pHash, app package.
- [ ] Two or more events sharing ≥ 2 entities within 30 days form a campaign object.
- [ ] Campaign objects carry first-seen, last-seen, channel set and observed lifecycle stage.
- [ ] **Resurfacing detection:** a template or asset reappearing after a takedown-consistent gap raises `campaign_resurfaced`. This is a documented real-world requirement — a fabricated deepfake video of a stock-exchange CEO required a *second* advisory in March 2026 after resurfacing following removal.
- [ ] Correlation runs entirely on-device. No campaign data leaves the machine on the default path.

---

### 5.B Authentication Requirements

> These requirements are the differentiator. They address the half of the problem statement that says: *"there are currently limited mechanisms to verify that a communication purportedly from SEBI, a stock exchange, a listed company, or a registered intermediary is genuine."*

---

#### F-B1 · Registration identity verification — **P0 · flagship**

New module `backend/engines/securities_identity.py`, mirrored as a lightweight check in `background.js`.

**Capabilities:** extract registration claims from text, page, image OCR and app listing → resolve against a bundled snapshot of SEBI's public intermediary register → fuzzy-match resolved name against the posting identity → detect collisions → check disclosure compliance for post-1-May-2026 content.

**Output states:**

| State | Meaning | Trust impact |
|---|---|---|
| `registration_valid` | Resolves, name matches, status active | **+25** |
| `registration_invalid` | Malformed or unresolvable | −40 |
| `registration_absent` | Securities content, no disclosure, dated ≥ 2026-05-01 | −20 |
| `registration_collision` | Resolves, but to a different entity than the poster | −45, emit `impersonation_alert` |
| `registration_weak_match` | Name similarity 70–84 | −10, flag only, **never accuse** |

**Acceptance criteria**
- [ ] Valid number on its own entity's domain → `registration_valid`, trust increases.
- [ ] Well-formed but unresolvable number → `registration_invalid`, number echoed in the reason string.
- [ ] Securities content, no disclosure, page date ≥ 2026-05-01 → `registration_absent`.
- [ ] Same number across ≥ 2 distinct handles in local history → `registration_collision` + `impersonation_alert`.
- [ ] **Negative case (zero-tolerance):** a genuinely registered adviser's content must *never* produce `registration_invalid` or `registration_absent`. Any occurrence is a P0 defect, not a tuning issue.
- [ ] Runs with the backend down — register snapshot is bundled, no network call.
- [ ] UI displays `Register data as of <date>` on every registration verdict.

**Design constraint (mandatory):** registration-number patterns must be **derived programmatically from the downloaded register file**, never hand-written from memory. Scan the register for distinct prefix families and generate the matcher. Any prefix present in the register but unmatched by the regex family is a defect in the matcher.

---

#### F-B2 · Payment namespace verification — **P0**

**Acceptance criteria**
- [ ] `upi_namespace_check(upi_id)` returns `{is_valid_handle, category, sebi_check_url}`.
- [ ] `xyz.brk@validhdfc` → `is_valid_handle: true, category: broker`.
- [ ] `investprofit99@ybl` → `is_valid_handle: false`, raises `payment_outside_valid_namespace`.
- [ ] Bank account + IFSC pairs extracted and routed to a SEBI Check deep link.
- [ ] Namespace list is bundled and versioned; absence of network does not disable the check.

---

#### F-B3 · Application integrity verification — **P1**

**Acceptance criteria**
- [ ] Play Store listings for securities apps are checked for the Verified App Label.
- [ ] Sideloaded APK links in messages raise `unverified_distribution`.
- [ ] Package-name similarity to registered intermediaries' known packages computed.
- [ ] Absence of a label is reported as `app_verification_absent`, **not** as "this app is malicious".

---

#### F-B4 · Sender and domain authentication — **P1**

For CH4 (email) and CH1 (web).

**Acceptance criteria**
- [ ] SPF, DKIM and DMARC results parsed from headers where the client exposes them; alignment failure raises `sender_authentication_failed`.
- [ ] Display-name spoofing detected: display name matches a registered intermediary, SEBI, or an exchange while the envelope domain does not.
- [ ] Official-domain registry (SEBI, NSE, BSE, NSDL, CDSL, AMFI, registered intermediaries) bundled; near-miss domains raise `official_domain_lookalike`.
- [ ] Lookalike detection covers homoglyph substitution and punycode.

---

#### F-B5 · Content provenance verification — **P0 (states) / P1 (full C2PA)**

**Acceptance criteria**
- [ ] Four states from `schemas/provenance_assessment.json` are rendered in the UI.
- [ ] `provenance_missing` renders as *"This content carries no verifiable credentials"* with an explicit *"this is not proof of deception"* line. **This rule is inherited verbatim from the system's own design law and must not be relaxed.**
- [ ] Where a manifest exists, signer identity and validity are shown.
- [ ] Known limitations are stated in-product: metadata is strippable, most content carries none, and re-encoding or screen-recording destroys it. Provenance raises confidence when present; its absence proves nothing.

---

#### F-B6 · Verified-channel and callback verification — **P1**

Implements the existing `channel_identity_packet` schema.

**Acceptance criteria**
- [ ] Verified **channel**, verified **sender**, verified **content** and **safe interaction** are reported as four separate truths and are never collapsed into one. *(Inherited design law.)*
- [ ] For a claimed brand, the system surfaces the official contact path from the bundled registry and recommends **callback-only** verification.
- [ ] The system never asserts verified caller identity without an identity rail — already an entry in `blocked_claims`.

---

#### F-B7 · Official document authentication — **P2**

**Acceptance criteria (design-for)**
- [ ] Interface exists for DigiLocker-issued holding statements and CAS.
- [ ] QR codes on official communications are decoded and routed to the issuing authority's verification endpoint where one exists.

---

### 5.C Alerting, Workflow and Evidence

#### F-C1 · Tiered alerting — **P0**
- [ ] Three tiers (LOW / MEDIUM / HIGH) mapped from the 0–100 trust score, with a distinct visual treatment and an icon for each.
- [ ] Colour is never the only signal.
- [ ] HIGH-tier interstitials interrupt before form submit and before payment focus, and are always dismissible.
- [ ] Confidence is always visible. **No certainty theatre.**

#### F-C2 · Reason codes — **P0**
- [ ] Every verdict renders ≥ 1 plain-language reason. No bare numeric score is ever displayed alone.
- [ ] Format: *"Claimed registration INA000XXXXXX is registered to Acme Advisers Pvt Ltd, not to this sender."* — not *"risk score 0.87"*.
- [ ] Reasons carry a source reference where one exists (SEBI advisory, register snapshot date, provenance signer).
- [ ] Reason codes are stable identifiers, so they can be counted, evaluated and audited — a Reg 16C requirement in practice.

#### F-C3 · Interception points — **P0** (extends existing)
- [ ] Page load, link hover, form submit, payment-field focus, WhatsApp Web message render, Telegram Web forwarded message, right-click on selection or media.
- [ ] Every interception is timed so the user can still walk away.
- [ ] The system **warns; it never acts on the user's behalf.**

#### F-C4 · Signed evidence packet — **P0**

Extends `schemas/recovery_case.json`:
```
securities: {
  registration_claims: [{ number, state, resolved_name, poster_identity, collision_handles[] }],
  payment_targets:     [{ upi_id, in_valid_namespace, category, sebi_check_url }],
  typologies_matched:  [{ id, weight, source_advisory_url }],
  provenance:          { state, credentials[], signer },
  ml_verdict:          { p_phishing, model_version, layer, top_features[] },
  campaign:            { campaign_id, first_seen, channels[], resurfaced }
}
signature: { alg: "ECDSA-P256-SHA256", key_id, value }
```
- [ ] Exports on explicit user action only.
- [ ] `python scripts/verify_evidence.py <packet.json>` prints VALID/INVALID.
- [ ] Contains no data class not declared in `module_registry.json`.
- [ ] Human-readable — a police officer or compliance officer can read it without tooling.

#### F-C5 · Recovery rail routing — **P0**

| Rail | Routing condition |
|---|---|
| **NCRP / 1930** | `lost_money = true` — always first, above everything |
| **SCORES** | No loss + entity resolves as a registered intermediary or listed company |
| **Chakshu / Sanchar Saathi** | No loss + suspicious communication + entity unregistered |
| **SEBI Check** | Before paying — verify UPI ID or account+IFSC |
| **SEBI intermediary search** | Verifying a claimed registration number |
| **I4C suspect repository** | Looking up a number / UPI / URL before acting |

- [ ] Nothing is filed automatically. The user clicks through, and the UI says so.

#### F-C6 · Impersonation alert to the legitimate holder — **P1**
- [ ] On `registration_collision`, produce a separate packet addressed to the *real* registration holder, containing impersonating handles, first-seen timestamps and content hashes.
- [ ] **Prepared only, never sent.** Consistent with "no hidden outreach".

#### F-C7 · Organisational console — **P1**

A local, read-only surface for P3/P4/P5. Extends the existing `glass_console` operator module.
- [ ] Aggregated view of collisions naming the operator's own registration numbers.
- [ ] Campaign objects with lifecycle and resurfacing state.
- [ ] Bulk evidence-packet export.
- [ ] Read-only. No enforcement action. No autonomous outreach.
- [ ] Runs from the same single Python process. No new infrastructure.

---

### 5.D Governance Requirements

#### F-D1 · Signed capability contracts — **P0** (extends existing)
- [ ] Every new module (`securities_identity`, `ml_lane`, `voice_lane`, `media_lane`, `campaign_lane`) is declared in `module_registry.json` with tier, capabilities, data classes, network hosts and guardrails.
- [ ] All registries re-signed; `validate_sandbox.py` passes.
- [ ] Signing key rotated; the prior key appears in `revocations.json`.
- [ ] New data classes added to `extension_policy.json`.

#### F-D2 · Model governance — **P0**
- [ ] Every model artefact carries `{model_version, trained_at, dataset_hash, feature_set_version}`.
- [ ] Every verdict names the model version that produced it.
- [ ] A documented rollback path to the previous model exists.
- [ ] A deterministic fallback path (registration check + local gate) remains available and is **immune to model drift** — if the ML layer degrades, the authentication layer still works.

#### F-D3 · Blocked claims — **P0**
Extend the existing `blocked_claims` list with:
- "this is a deepfake" / "this voice is synthetic" / "AI-generated" as verdicts
- "verified safe"
- "SEBI-approved" / "SEBI-registered" as a claim about the tool itself
- any assertion of synthetic origin without provenance evidence

- [ ] A CI check fails the build if any blocked claim string appears in user-facing copy.

---

### 5.E Integration Points with Market Infrastructure

All integrations are built as **adapters with a bundled-snapshot fallback**, so the system works today with public data and becomes live with a credential, not a rewrite.

| # | Integration | What it provides | Access reality | Priority |
|---|---|---|---|---|
| **I1** | **SEBI intermediary register** | Ground truth for F-B1 | Public; bundled snapshot | **P0 — blocks F-B1** |
| **I2** | **SEBI Check** | UPI ID / account+IFSC verification | Public portal; deep-link where constructible, else "open SEBI Check" | **P0** |
| **I3** | **`@valid` UPI namespace list** | Payment authentication | Public; bundled | **P0** |
| **I4** | **SEBI circulars / advisories** | Typology corpus + citable sources | Public | **P0** |
| **I5** | **Recovery rails** (Chakshu, NCRP/1930, I4C, NPCI, SCORES) | Official reporting | Public URLs | **P0** |
| **I6** | **Verified App Label / Play Store metadata** | App authentication | Public | P1 |
| **I7** | **Official-domain registry** (SEBI, NSE, BSE, NSDL, CDSL, AMFI) | Sender/domain authentication | Public; bundled | P1 |
| **I8** | **C2PA / Content Credentials** | Media provenance | Open standard, `c2pa-rs` | P1 |
| **I9** | **CERT-In advisories** | Malware and infrastructure IoCs | Public | P1 |
| **I10** | **DoT FRI / DIP + MNRL** | Mobile-number risk class, revoked numbers | API for regulated entities — **adapter only** | P2 |
| **I11** | **I4C suspect-identifier registry** | Suspect indicators, mule accounts | Institutional — **adapter only** | P2 |
| **I12** | **DigiLocker** | Authenticated holding statements, CAS | Consumer-consented | P2 |
| **I13** | **SEBI SI Portal** | Live intermediary lookup | Institutional — **adapter only** | P2 |

**Requirement I-ALL:** every integration must declare `{source, licence, fetched_at, record_count}` and the UI must show data recency wherever an integration result is displayed.

---

## 6. Non-Functional Requirements

### NFR-1 · Performance

| Path | p50 | p95 |
|---|---|---|
| Cache hit → badge painted | 5 ms | 15 ms |
| Local gate (18 rules) | 3 ms | 8 ms |
| ML layer 1.5a (in-extension) | 4 ms | 10 ms |
| ML layer 1.5b (backend) | 20 ms | 50 ms |
| Registration identity check (offline) | 10 ms | 30 ms |
| **Full verdict, backend up** | 80 ms | **250 ms** |
| **Full verdict, fully offline** | 15 ms | **50 ms** |
| LLM lane (escalated cases only) | 1.2 s | 3 s |
| Voice transcription, 30 s note | — | 20 s |
| Extension memory | — | < 80 MB |
| Backend cold start | — | < 4 s |

### NFR-2 · Reliability and offline-first
- Every P0 verdict path must complete with the network disabled and the backend stopped. This is a hard requirement, not a nice-to-have: an AI check that requires a fast connection is useless to the people most exposed to fraud, who are frequently the ones on the worst networks — and India's investor growth is concentrated exactly there, with 27% of the investor base now outside the top ten states and north-eastern states up 7–9× since FY21.
- Chain degradation is transparent — the sidepanel always names which layer produced the verdict.
- No single component failure removes protection; worst case is the 18-rule gate.

### NFR-3 · Scalability
- Consumer tier: single user, local, no server-side state.
- Organisational tier (F-C7): ≥ 100,000 events and ≥ 10,000 campaign objects in SQLite with p95 query < 200 ms.
- Tiered evaluation — expensive lanes (LLM, media forensics, transcription) run only on candidates already flagged cheaply, capped at ≤ 25% of traffic.
- Horizontal scaling is explicitly **not** a requirement. The architecture is one process per deployment.

### NFR-4 · Security
- Contract integrity: ECDSA P-256/SHA-256 on all registries; private key never distributed; rotation documented.
- Evidence packets signed and independently verifiable.
- Backend binds `127.0.0.1` only; no external listener.
- MV3 `host_permissions` kept minimal and in sync with any configured origin.
- No secrets in the repository; `secrets_loader` remains the only path.
- Threat feeds are treated as untrusted input and never executed or interpolated into code.
- Dependency count minimised deliberately — a smaller supply chain is a security property, not just a simplicity one.

### NFR-5 · Privacy and data protection
- **DPDPA 2023 / DPDP Rules 2025.** Consent-first. The Act does not recognise legitimate interest, so reliance on the s.17(1)(c) exemption (prevention, detection, investigation of offences) is documented in `docs/SECURITY_AND_LEGAL_CONTROL_MATRIX.md` and **bounded, not assumed**. Full substantive compliance date: 13 May 2027.
- Data minimisation by default: on-device computation, transmit scores not raw content.
- Every data class touched is declared in `module_registry.json` and shown in the options page.
- Retention: local history capped and user-clearable; no server-side persistence on the consumer path; evidence export user-initiated only.
- No processing of a third party's personal data except as incidental to content the user has themselves received.
- No profiling of named individuals. Entity resolution is scoped to registration numbers, domains, handles and payment identifiers.

### NFR-6 · Regulatory compliance
| Instrument | Requirement placed on this system |
|---|---|
| **SEBI CSCRF** (Aug 2024) | Where deployed inside a regulated entity: SOC/M-SOC compatibility, 6-hour incident reporting support, SBOM published, VAPT-ready, auditable by CERT-In-empanelled organisations |
| **SEBI (Intermediaries) Amendment Regs 2025, Reg 16C** | The deploying entity is **solely liable for AI output** — therefore every verdict is explainable, versioned, attributable and auditable (F-C2, F-D2) |
| **SEBI AI/ML guidance (Jun 2025)** | Governance framework, testing and continuous monitoring, explainability, human oversight, documented fallback, bias checks, disclosure that AI is in use |
| **IT Amendment Rules 2026** (in force 20 Feb 2026) | SGI labels and provenance metadata are consumed and surfaced, never stripped; no synthetic-origin assertions without evidence |
| **DPDPA / DPDP Rules 2025** | See NFR-5 |
| **SEBI advertising and disclosure norms** | The tool makes no return claims, no investment recommendations, and no "SEBI-approved" claim about itself |

### NFR-7 · Accessibility and language
- English + Hindi for all P0 warning copy, in `extension/i18n/`. Marathi, Bengali, Tamil, Telugu, Gujarati as P1.
- Warning copy at ≤ Class 8 reading level. Short sentences. No jargon.
- WCAG 2.1 AA contrast on all warning surfaces; keyboard-navigable sidepanel; screen-reader labels on every state.
- Every state has an icon and a text label — colour is never the only signal.

### NFR-8 · Trust UX laws (inherited, now enforceable)
1. No certainty theatre — confidence is always visible.
2. Never collapse channel trust, sender trust, content trust and safe interaction.
3. Missing credentials are never presented as proof of deception.
4. The user can always proceed. The system informs; it does not gate.
5. Nothing is sent, filed or reported without an explicit user action.
6. Score separately from action eligibility; action separately from recovery.

### NFR-9 · Simplicity constraint (explicit)
- **No Docker, no Kubernetes, no bundler, no message queue, no database server, no cloud account, no paid API required to run.**
- Installation: `pip install -r backend/requirements.txt`, `uvicorn backend.main:app --port 8799`, "Load unpacked".
- Total new Python dependencies: **≤ 10**.
- Ollama is optional and its absence degrades gracefully.
- Any proposal adding a service, container or hosted dependency must be rejected or moved to P2.

### NFR-10 · Maintainability and observability
- `ml/features.py` is the **single definition** of the feature set. `content_script.js` emits exactly those names in exactly that order; `eval/parity_test.py` enforces it. Two feature definitions must never exist.
- Structured local logs with a verdict trace: layer, latency, reason codes, model version.
- Every dataset carries a provenance line: source, licence, fetch date.
- Reason codes are stable identifiers so they can be counted over time.

### NFR-11 · Testability and evidence
- The evaluation harness (§7) is a **release blocker**, not a deliverable.
- Every performance and accuracy number in any external material must trace to a line in `eval/REPORT.md`.

---

## 7. Success Metrics

The problem statement asks for *"clear evidence of detection or authentication performance."* These are the numbers that constitute that evidence.

### 7.1 Detection performance

> **Target revised 2026-08-07 on the evidence of `eval/corpus_audit.py`.** The URL-model MCC
> target was **≥ 0.85**. That figure was written before anyone opened the corpus. The audit shows
> 100% of PhiUSIIL's legitimate URLs are canonicalised `https://www.<domain>` homepages with no
> path and no query, so 0.85 is not reachable honestly on this corpus — and *is* reachable
> dishonestly: 34 artefact-bearing features score MCC 0.99 and flag every legitimate deep link,
> including SEBI's own register URL. The target moved rather than the feature set. See
> `eval/REPORT.md` §B.0 (the audit) and §B.2 (the rationale).

| Metric | Success | Stretch | Method |
|---|---|---|---|
| **MCC** (primary — phishing sets are imbalanced, accuracy flatters) | **≥ 0.55 on a domain-grouped split with artefact-stripped features** | ≥ 0.65 | `GroupShuffleSplit` by registrable domain; features from the `www.`-stripped hostname only, ignoring scheme, path and query; 95% bootstrap CI, 1,000 stratified resamples. Rationale: `eval/corpus_audit.py` |
| **Recall @ FPR ≤ 1%** | ≥ 0.85 | ≥ 0.92 | Threshold chosen to hold FPR ≤ 1% while maximising MCC |
| **PR-AUC** | ≥ 0.90 | ≥ 0.95 | Held-out temporal test set |
| **Brier score** (calibration) | ≤ 0.12 | ≤ 0.08 | With reliability diagram |
| **FPR on legitimate cohort** | ≤ 1.0% | ≤ 0.5% | ≥ 100 curated legitimate samples |
| **ΔMCC under few-shot LLM paraphrase** | ≥ −10 pp | ≥ −5 pp | Adversarial set; benchmark comparison: zero-shot paraphrase costs Naive Bayes 5.3 pp, Logistic Regression 6.1 pp, GPT-4 3.2 pp; few-shot costs SVM 9.0 pp |
| **LLM invocation rate** | ≤ 25% | ≤ 15% | Fraction of scans escalated past Layer 1.5 |

### 7.2 Authentication performance

| Metric | Success | Stretch |
|---|---|---|
| **Registration-claim resolution precision** | ≥ 95% | ≥ 99% |
| **False `registration_invalid` on genuinely registered entities** | **0** | 0 |
| **Collision detection recall** (seeded impersonation fixtures) | ≥ 90% | ≥ 95% |
| **UPI namespace classification accuracy** | ≥ 99% | 100% |
| **Disclosure-compliance detection accuracy** (post-1 May 2026 content) | ≥ 95% | ≥ 98% |
| **Provenance state assignment accuracy** | ≥ 98% | ≥ 99% |

### 7.3 System performance
Per NFR-1. Measured, tabulated in `eval/REPORT.md`, never asserted.

### 7.4 User-outcome metrics (post-pilot, lagging)

| Metric | Target |
|---|---|
| **Lead time to intervention** — days between first alertable signal and first material transfer | ≥ 7 days median |
| Interstitial abandonment rate on HIGH verdicts | ≥ 60% |
| Evidence packets accepted without enrichment by a recovery rail | ≥ 80% |
| Collision alerts rated actionable by a real intermediary | ≥ 70% |
| Warning comprehension (Hindi cohort, think-aloud test) | ≥ 80% correctly state the reason |

> **Note on lead time.** This is the metric that matters most and the one nobody measures. Securities social-engineering campaigns run for weeks — documented Indian cases show three months from first contact to collapse — which means the detection window is orders of magnitude larger than in card fraud. The system is designed to catch a *campaign*, not a transaction.

### 7.5 Reporting requirement
`eval/REPORT.md` must contain, regenerable by one command: MCC + CI, confusion matrix, PR-AUC, Recall@FPR≤1%, Brier + calibration plot, per-layer ablation (regex-only → +lexical → +DOM → +securities-identity → full fusion), latency table p50/p95, LLM invocation rate, adversarial degradation, legitimate-cohort FPR, and Wilcoxon signed-rank significance against the v6.2 regex-only baseline.

**Both a temporal split and a random split must be reported**, with the random split explicitly labelled *"optimistic — leaks campaign templates across the split"*. Showing that you know the difference is a credibility gain, not a weakness.

---

## 8. Constraints and Assumptions

### Constraints
| # | Constraint |
|---|---|
| C1 | No Docker, no containerisation, no orchestration |
| C2 | ≤ 10 new Python dependencies; no Node build step |
| C3 | Chrome/Chromium MV3 only for this release |
| C4 | No institutional API access assumed (SI Portal, FRI/DIP, I4C) — adapters + snapshots only |
| C5 | No paid API required to run the system |
| C6 | Existing design laws from `delta_pack_v2`/`v3` are binding, not advisory |
| C7 | `extension_policy.json` `blocked_claims` and `release_blockers` are binding |

### Assumptions
| # | Assumption | Risk if wrong |
|---|---|---|
| A1 | SEBI's intermediary register is publicly obtainable in a machine-readable form | **High** — blocks F-B1. Mitigation: hand-curate a bounded subset and disclose the record count. |
| A2 | Registration-number formats are inferable from the register file | Medium — mitigated by deriving patterns from data, not memory |
| A3 | `@valid` namespace membership is publicly listable | Medium — fallback is suffix-pattern matching plus a SEBI Check deep link |
| A4 | Users will install a browser extension | Accepted; mobile companion is P2 |
| A5 | Sufficient labelled data exists for MCC ≥ 0.85 | Medium — mitigation is to report the honest number with its CI. A measured 0.78 is worth more than a claimed 0.99. |

---

## 9. Traceability to the Problem Statement

| Problem statement asks for | Delivered by |
|---|---|
| Detect hyper-personalised LLM phishing emails | F-A1, F-A2, F-B4, CH4 |
| Detect synthetic voice calls impersonating executives/regulators | F-A3, F-B6, CH5 |
| Detect deepfake videos of CEOs, CIOs, market experts | F-A4, F-B5, CH6 |
| Detect AI-generated social content manipulating retail behaviour | F-A1, F-A7, F-B1, CH7 |
| Protect brokers, investors and MIIs | Personas P1–P5; F-C6, F-C7 |
| **Verify communications from SEBI, exchanges, listed companies, registered intermediaries** | **F-B1 through F-B7** — the half most solutions omit |
| Specify the target user | §3 — P1/P2 primary, P3/P4/P5 secondary |
| Specify the channels addressed | §4 — CH1–CH7 |
| **Clear evidence of detection or authentication performance** | §7 + `eval/REPORT.md` (release blocker) |
| Improve ability to identify, flag or **respond** | F-C4 evidence packet, F-C5 rails, F-C6 impersonation alert |

---

## 10. Glossary

| Term | Meaning |
|---|---|
| `@valid` | NPCI-issued UPI namespace exclusive to SEBI-registered intermediaries, with category suffixes (`.brk`, `.mf`) |
| **SEBI Check** | SEBI facility for verifying an intermediary's UPI ID or bank account + IFSC |
| **SCORES** | SEBI Complaints Redress System |
| **Chakshu** | Sanchar Saathi facility for reporting suspected fraud communication |
| **NCRP / 1930** | National Cyber Crime Reporting Portal and helpline |
| **I4C** | Indian Cyber Crime Coordination Centre |
| **CSCRF** | SEBI Cybersecurity and Cyber Resilience Framework |
| **Reg 16C** | SEBI (Intermediaries) Amendment 2025 provision placing sole liability for AI output on the deploying entity |
| **SGI** | Synthetically Generated Information, as defined in the IT Amendment Rules 2026 |
| **C2PA** | Coalition for Content Provenance and Authenticity — content credentials standard |
| **MCC** | Matthews Correlation Coefficient — imbalance-robust classification metric |
| **Collision** | One registration number claimed by two or more distinct identities |
| **Campaign object** | A cluster of events linked by ≥ 2 shared entities within a time window |
| **Allowlist reasoning** | Detecting the absence of a legally-required credential, rather than the presence of a badness signal |
