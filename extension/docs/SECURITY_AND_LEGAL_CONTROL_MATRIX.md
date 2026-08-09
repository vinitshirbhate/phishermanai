# Phisherman AI Browser Guard Sandbox — Security and Legal Control Matrix

Last reviewed: 2026-03-09

## Product truth

This sandbox is a local browser-protection prototype. It is not a browser engine, not a full device monitor, and not a government service.

Non-negotiable product constraints:

- The browser layer can assess pages, links, forms, screenshots, and user-submitted content.
- The browser layer cannot directly read native WhatsApp chats, SMS inboxes, or phone calls without a separate companion app.
- Workflow agents must remain approval-gated.
- No module may introduce hidden network egress.
- No result may claim certainty, safety, or legal authority.

## Security controls in this build

| Area | Control |
|---|---|
| Extension permissions | Locked to `activeTab`, `storage`, `sidePanel` |
| Network egress | Locked to `http://127.0.0.1:8799/*` |
| Side effects | Disabled by default; agents do not send, file, or report anything |
| Submit interception | Only prompts on high-risk pages and high-risk forms |
| Module law | Each module declares capabilities, data classes, network hosts, and approval need |
| Agent law | Each agent declares guardrails and cannot run silently |
| Logging | No backend request log is enabled by default |
| Evidence export | Explicit user action only |
| Drift detection | `scripts/validate_sandbox.py` fails on permission or contract drift |
| Contract trust | Detached signatures required for policy, module, and agent registries |
| Revocation | Trusted signer list and revocation file are checked during validation |

## Bundled SEBI register — data minimisation decision (DPDPA)

**Decision.** We ship SEBI's public register of registered intermediaries inside the extension, with personal-data fields stripped before bundling.

**Source.** `https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes` — Research Analyst (`intmId=14`) and Investment Adviser (`intmId=13`). Fetched by `scripts/fetch_sebi_register.py`; per-category as-on dates recorded in `registry_meta.per_category_as_on_dates`.

**What SEBI publishes per registrant, and what we do with it:**

| Field | SEBI publishes | We ship | Rationale |
|---|---|---|---|
| Registration No. | yes | **yes** | The credential being authenticated. Not personal data. |
| Name | yes | **yes** | The registered entity name; the claim we resolve against. |
| Validity dates | yes | **yes** | Bounds the assertion in time. |
| E-mail | yes | **domain only** | The domain is a weak identity anchor. The local part is personal data and is discarded at parse time. |
| Address | yes | **no** | Home address for individual proprietors. |
| Correspondence address | yes | **no** | As above. |
| Telephone | yes | **no** | Personal mobile for individual proprietors. |
| Fax No. | yes | **no** | No verification value. |
| Contact Person | yes | **no** | A named third party who is not the subject of the check. |

**Why minimise something already public.** Roughly a third of these registrants are individual proprietors for whom the published address is a home address and the published telephone is a personal mobile. Publication by a regulator for a supervisory purpose does not license redistribution for a different purpose. Bundling ~3,000 individuals' home addresses and personal phone numbers inside a Chrome extension distributed to arbitrary users would create a new, uncontrolled copy of that data on every install, serving no function the product needs — the identity check requires only the number, the name and a domain. That is a plain purpose-limitation and data-minimisation failure under the DPDPA regardless of the source being public, and it is a question a reviewer should be expected to ask.

**Enforcement.** `backend/tests/test_sebi_register.py` fails the build if any address, telephone, fax, contact-person or full-e-mail field appears in `backend/data/sebi_register.json` or `extension/data/securities_snapshot.json`. Raw HTML retaining the dropped fields is cached under `scripts/.cache/`, which is gitignored and never distributed.

**Accuracy posture.** The register lists *current* registrants only — a cancelled or lapsed registration disappears from it rather than appearing with a cancelled status. The `invalid` verdict therefore reads "Not found in the SEBI register as of `<per-category date>`" and never asserts that a number is fabricated. Every registration verdict, valid and invalid alike, displays the per-category as-on date and a "Verify live on SEBI" link to the source page.

**Scope bound.** Only the categories listed in `registry_meta.covered_categories` are resolvable. A well-formed number outside them (a Stock Broker's `INZ…`, say) returns `unverified`, never `invalid` — treating a coverage gap as an accusation against a genuine intermediary is the worst defect class in this system.

## Legal-risk posture

This sandbox mitigates the highest-risk product-law failure modes, but it is not yet sufficient for production launch.

### Claims we must not make

- "safe"
- "100% scam detection"
- "guaranteed protection"
- "zero data collection"
- "works on phone calls and native chats without an app companion"
- "government approved" or "government affiliated"

### Production blockers still open

1. A real launch needs production signing custody and rotation, not just the sandbox dev signer.
2. A real launch needs assigned operator identity, breach ownership, and incident response.
3. A real launch needs extension-store review and a public dispute-resolution path for flagged entities.
4. A real launch needs encryption-at-rest for retained subscriber and evidence data outside the browser.
5. A real launch needs the mobile-companion privacy contract implemented before call/message claims are made.

## Recommended legal/operational line for launch

- Free core safety is acceptable.
- Premium modules are acceptable.
- Baseline safety must not be paywalled.
- Fact checking must be clearly separated from scam scoring.
- Any family or guardian workflow must be opt-in and reversible.
- Any marketplace must start curated, signed, reviewed, and revocable.
- Mobile-companion permissions must remain separate from browser claims and browser onboarding.

## Official references informing this matrix

- Chrome Side Panel API: https://developer.chrome.com/docs/extensions/reference/api/sidePanel
- Chrome extension permission warnings: https://developer.chrome.com/docs/extensions/develop/concepts/permission-warnings
- Chrome built-in AI overview: https://developer.chrome.com/docs/ai/built-in
- Android NotificationListenerService: https://developer.android.com/reference/android/service/notification/NotificationListenerService
- Android CallScreeningService: https://developer.android.com/reference/android/telecom/CallScreeningService
- Google Play restricted permissions: https://support.google.com/googleplay/android-developer/answer/9888170
- Digital Personal Data Protection Rules, 2025 (Gazette staging): https://egazette.gov.in
