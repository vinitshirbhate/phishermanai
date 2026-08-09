# Phisherman AI

**A Chrome extension that warns Indian retail investors about securities fraud — before they click, install, or pay.**

Built for **SEBI Securities Market Hackathon — PS-01**, _AI-Driven Detection of Synthetic Media and Phishing Attacks in Securities Markets_.

No build step · No npm · Works with the network off · Nothing leaves your device

[Architecture](#architecture) · [Try it in 5 minutes](#try-it-in-5-minutes) · [The numbers](#the-numbers-including-the-bad-ones) · [Evaluation report](eval/REPORT.md)

---

## The problem, in one message

Someone sends your uncle a WhatsApp message:

> _"SEBI-registered advisor. Guaranteed 40% returns. VIP group closing today. Pay to `investprofit99@ybl`."_

Then a file: `Zerodha_Kite_Pro_Unlocked.apk`. Then a link that looks almost exactly like his broker's site.

He loses his savings.

## Why the usual approach fails

Most scam blockers keep a list of known-bad websites. That list is always a day behind — fraudsters change domains daily, and by the time a domain is on a blocklist it has done its work.

**We ask a different question.**

SEBI requires every legitimate adviser, broker and research analyst to display a registration number, and to take money only through a verified `@valid` UPI handle. So instead of hunting for signs of a scam, we check whether **the credential the law requires is actually there — and whether it really belongs to whoever is showing it.**

That puts a scammer in a trap with no exit:

| They...                        | And then                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| **Keep** a registration number | We resolve it against the real SEBI register and catch that it belongs to _someone else_ |
| **Remove** it                  | The page is breaking a disclosure rule mandatory since 1 May 2026                        |

A fraudster can rewrite their sales pitch endlessly. They cannot fake a number that resolves to a real registered firm.

---

## Architecture

### The flow, end to end

![Extension flow](docs/architecture-extension.svg)

Four inputs, one question each, merged into a single verdict that carries its own reasoning. Source: [`docs/architecture-extension.excalidraw`](docs/architecture-extension.excalidraw).

**Merge signals** is where four independent checks — which know nothing about each other — become one answer. Each finding gets classified by _its own meaning_ (risk / protective / context), deduplicated, ordered worst-first, and combined with a **floor-only** rule: an APK finding can drag trust down, but a benign attachment can never lift a page that already looks dangerous.

**Verdict** is not a score. It's a code plus its evidence plus its provenance — and every finding stays tagged with which of four truths it speaks to: _identity_, _content_, _channel_, _interaction_. They're never collapsed into one number, because "this chat behaves oddly" and "this registration belongs to someone else" are different claims with different consequences.

### The full system

![System architecture](docs/architecture.svg)

Source: [`docs/architecture.excalidraw`](docs/architecture.excalidraw). Regenerate both with:

```bash
python scripts/gen_extension_flow.py && python scripts/gen_architecture_diagram.py
python scripts/excalidraw_to_svg.py --all
```

### The four lanes

| Lane                               | Question                             | How                                                                                                                                                                  |
| ---------------------------------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Links** `preflight/`             | Is this domain really who it claims? | Public Suffix List, so `paytm.evil.co.in` resolves to `evil.co.in`. Homoglyph and punycode detection. IP literals in decimal/octal/hex. Redirect chains.             |
| **Advisors** `securities_identity` | Is that SEBI number real?            | 3,179 real registrants scraped from SEBI's public register (IA + RA categories). Pattern **derived from the data**, with a load-time assertion it matches every row. |
| **Chats** `whatsapp/`              | Does this chat behave like a scam?   | Reply-timing uniformity, escalating money asks, template reuse across groups — computed from timing and hashes, without reading content.                             |
| **Files** `shared/apk_check`       | Should you install that APK?         | Filename + delivery channel. `Spotify (Premium) Mod2.apk` → app file sent in chat, advertises a paid app unlocked free.                                              |

> **One design call worth calling out.** We deliberately do _not_ fold lookalike letters when comparing identity. Folding makes Cyrillic `nsеindia.com` compare **equal** to the real NSE domain — the tool would actively vouch for the impostor. Missing an attack is bad; endorsing one is worse.

---

## The one rule everything obeys

**Never cry wolf.** A tool that flags your real bank gets uninstalled by Tuesday.

This is enforced by machines, not good intentions:

| Gate               | What it does                                                                                                                           |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| **G-2**            | Counts false accusations on every eval run. Target 0. **Currently 0.**                                                                 |
| **Blocked claims** | `"safe"`, `"verified safe"`, `"guaranteed protection"`, `"this is a deepfake"` cannot appear in user-facing text. **The build fails.** |
| **Parity**         | The JS and Python feature implementations must agree to ±0.02, or CI fails                                                             |
| **Reachability**   | A module that is built and never loaded fails the suite — twice caught real dead code                                                  |
| **Provenance**     | Every answer names its sources and dates                                                                                               |

That last one is the difference between a shrug and an answer. A clean link doesn't say "Safe ✓". It says:

```
Checked — www.marxists.org
Not listed on 3 blocklists covering 819,572 domains, as of 2026-03-23.
A domain registered since then would not appear.
```

Dated, checkable, and honest about what it can't see.

---

## Try it in 5 minutes

```bash
# 1. Load the extension
chrome://extensions/ → Developer mode → Load unpacked → select extension/

# 2. Serve the demo pages
python -m http.server 8801

# 3. Optional — the backend adds 820k blocklisted domains + impersonation detection
cd backend && pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8799
```

### The flagship demo — impersonation

Open **http://localhost:8801/demo/securities_scam_page.html**

| Look at                              | You should see                                                                                         |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Badge                                | Low trust, red                                                                                         |
| Side panel → **Securities Identity** | **Registration collision**                                                                             |
| Reason                               | _"Registration INA000000383 is registered to V R WEALTH ADVISORS PRIVATE LIMITED, not to this sender"_ |
| UPI row                              | `investprofit99@ybl` — outside `@valid`, with a SEBI Check link                                        |
| Footer                               | _"Register data as of 2026-08-06"_                                                                     |

The page calls itself _Alpha Wealth Circle_ and quotes `INA000000383` — a **real registration number from SEBI's public register**, held by a different firm entirely. That mismatch _is_ the detection, and no amount of rewriting the sales copy removes it.

> **Coverage caveat, stated up front:** the bundled register covers the **IA** (investment adviser) and **RA** (research analyst) categories — 3,179 real registrants. A broker number (`INZ…`) returns _"could not be checked — outside this snapshot's categories"_, never _"invalid"_. Absence of coverage is never reported as evidence of fraud.

### The demo that matters just as much

Open **http://localhost:8801/demo/safe_page.html** → high trust, no securities card, no warnings.

A tool that flags everything is useless. Showing it stays quiet is half the pitch.

### Offline — pull the plug

Stop the backend, turn Wi-Fi off, reload the scam page. **You still get a verdict**, with an "offline check" note. The registration lookup runs on-device in ~0.1 ms.

### Hover any link

You get the real registrable domain, what was checked, and what that check does _not_ cover. Shortened links can optionally be resolved to their true destination — off by default, and links carrying one-time tokens (password resets, unsubscribe) are **never** followed, because opening one would consume it.

---

## The numbers, including the bad ones

```
164 tests · 5 CI gates · G-2 false accusations: 0
```

| Metric                | Result                        | Target |     |
| --------------------- | ----------------------------- | ------ | --- |
| MCC (URL model)       | **0.6646** (CI 0.6597–0.6697) | ≥ 0.55 | ✅  |
| Recall @ FPR ≤ 1%     | 0.6112                        | ≥ 0.85 | ❌  |
| Brier                 | 0.1317                        | ≤ 0.12 | ❌  |
| G-2 false accusations | 0                             | 0      | ✅  |

**We publish the failures on purpose.** Here's the one worth reading:

The standard public phishing dataset everyone benchmarks on reports ~99% accuracy. We audited it. **100% of its "legitimate" URLs are tidy `https://www.domain` homepages** with no path and no query — while its phishing URLs are deep links. A model handed those columns learns _URL formatting_, scores 0.99, and flags SEBI's own website at p=1.000.

So we stripped scheme, `www`, path and query, split by registrable domain, and reported **0.66**. It's a worse number measuring a real thing.

```bash
python eval/run_eval.py      # regenerates eval/REPORT.md — nothing is hand-typed
```

---

## Verify it yourself

```bash
python -m pytest tests backend/tests -q     # 164 passed
node eval/preflight_harness.js              # 17/17, 0 false accusations
python eval/run_eval.py                     # G-2: 0
python eval/parity_test.py                  # PARITY_PASS
python scripts/check_blocked_claims.py      # BLOCKED_CLAIMS_PASS
```

---

## Honest status

**Works and is measured:**

- Registration collision detection against 3,179 real SEBI registrants, offline
- Coverage is **IA and RA only**. Broker (`INZ`) and other prefixes return "could not be checked", never "invalid" — a coverage limit is not a finding
- Link preflight: 17/17 on its harness, zero false accusations on the legitimate-domain guard set
- Blocklist lookup across 819,572 domains with dated provenance
- APK offer analysis, including fake-broker filenames
- Behavioural lane — scores what a message _does_, not what it's about

**Built but not yet running in a browser:**

- The WhatsApp lane's modules are complete and tested, but `adapter.start()` has no caller — no badge appears on a real WhatsApp page yet
- Chat context is not fed into the SEBI-disclosure rule; `enable_chat_context()` refuses unless explicitly confirmed

**Not verified:**

- WhatsApp and Gmail DOM selectors have never run against live markup. Fixtures we write would match selectors we wrote, and prove nothing. This needs human-captured snapshots.

**Not built:** voice analysis, C2PA parsing, email integration, org console.

Threat feeds are dated **2026-03-23**. The UI shows that date rather than hiding it.

---

## What's actually novel here

Most entries in this space are a keyword list with a score attached — flag everything, demo well, uninstalled in a week.

The engineering here went into **not being wrong**. The bug hunt is the demo. Real defects found and fixed in this codebase:

- A genuine internship email flagged as a **lottery scam** — the scanner was reading the _whole Gmail page_, including other people's promotional mail, and attributing it to the open message
- **Every email address on earth** read as a payment ID — `support@sebi.gov.in` parsed as a UPI handle
- _"Domain is on trusted whitelist"_ — a **positive** signal — rendered as a red danger warning, in three separate places
- **820,000 blocklisted domains that had never once matched**, because three feeds ship in three different file formats and nobody had checked
- An entire analysis lane that loaded perfectly and was **never called**

Each one is now pinned by a regression test that fails against the old code.

> Every other tool tells you it caught something.
> This one tells you what it checked, when, and what it still can't see.

---

## Glossary

| Term                    | Meaning                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------ |
| **SEBI**                | India's securities market regulator                                                  |
| **Registration number** | The licence ID (e.g. `INZ000031633`) every SEBI-registered intermediary must display |
| **`@valid` UPI**        | A UPI handle only registered intermediaries can use, e.g. `firm.brk@validhdfc`       |
| **Collision**           | One registration number claimed by two different identities — impersonation          |
| **Reason code**         | A plain-language explanation of _why_ you were warned, never just a number           |
| **MCC**                 | Matthews Correlation Coefficient — an imbalance-robust accuracy metric               |
| **G-2**                 | The zero-false-accusation gate                                                       |

---

**The system warns — it never acts for you.** Nothing is blocked, sent, replied to, forwarded, or reported without your click. No page content, message text, or payment identifier leaves your device on the default path.

[Implementation record](implementation04.md) · [Evaluation report](eval/REPORT.md) · [Testing guide](TESTING.md)
