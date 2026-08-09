# Phisherman AI Browser Guard — Source and Dataset Map

Last reviewed: 2026-03-09

This is the recommended ingestion stack for Phisherman AI. Official and verifiable sources should outrank news, commentary, or scraped rumor feeds.

## India-first official sources

| Source | Use |
|---|---|
| CERT-In Cyber Swachhta and alerts — https://cert-in.org.in/ | Government incident advisories and threat context |
| National Cyber Crime Portal — https://www.cybercrime.gov.in/ | Official reporting path |
| Sanchar Saathi / Chakshu — https://www.sancharsaathi.gov.in/sfc/ | Telecom fraud and spoofing response |
| I4C suspect repository — https://cybercrime.gov.in/Webform/suspect_search_repository.aspx | Search suspicious numbers, URLs, UPI IDs, and accounts before acting |
| RBI financial education / fraud awareness — https://www.rbi.org.in/FinancialEducation/fame.aspx | Payment and banking fraud guidance |
| RBI Complaint Management System — https://cms.rbi.org.in/ | Escalation path after an unresolved bank or payment complaint |
| NPCI fraud awareness — https://www.npci.org.in/what-we-do/upi/cyber-awareness | UPI-specific scam guidance |
| PIB Fact Check — https://pib.gov.in/aboutfactchecke.aspx | Government-claim verification |

## Fact-check and claim-verification sources

| Source | Use |
|---|---|
| Google Fact Check Tools API — https://developers.google.com/fact-check/tools/api/reference/rest | Structured claim-review retrieval |
| Google Fact Check structured data — https://developers.google.com/search/docs/appearance/structured-data/factcheck | Claim-review publishing pattern |

## Channel identity and messaging patterns

| Source | Use |
|---|---|
| Meta Verified for WhatsApp businesses — https://about.fb.com/news/2024/06/new-ai-tools-meta-verified-and-more-for-businesses-on-whatsapp/ | Business identity and impersonation-resistance patterns |
| Truecaller Secure Call — https://docs.truecaller.com/truecaller-for-business/features/secure-calls/how-does-secure-call-work | Verified caller pattern for banks, fintech, and support desks |
| Monzo Call Status — https://monzo.com/help/monzo-fraud-category/monzo-call-status-web | Strong in-app callback verification pattern |
| Google RCS for Business — https://developers.google.com/business-communications/rcs-business-messaging/guides/get-started/how-it-works | Carrier-grade branded messaging pattern |
| Telegram Mini Apps — https://core.telegram.org/bots/webapps | Rich stateful companion surface for MirrorMesh Lite |

## Assistive and vernacular layers

| Source | Use |
|---|---|
| Project BHASHINI / Bhasha Daan — https://bhashini.gov.in/bhashadaan/en/home | Language-access and translation path for multilingual scam support flows |

## Provenance and integrity sources

| Source | Use |
|---|---|
| C2PA — https://c2pa.org/ | Content Credentials and provenance standard |
| C2PA conformance — https://c2pa.org/conformance/ | Validator and trust-list program |
| C2PA Rust SDK — https://github.com/contentauth/c2pa-rs | Open-source verifier path |
| C2PA Android SDK — https://github.com/contentauth/c2pa-android | Native mobile provenance path |
| Play Integrity API — https://developer.android.com/google/play/integrity | Official-app integrity checks |
| Android Key Verifier — https://developer.android.com/privacy-and-security/key-verifier | System-backed verification for trusted surfaces |

## Network and identity APIs

| Source | Use |
|---|---|
| Open Gateway sandbox — https://developers.opengateway.telefonica.com/docs/sandbox | Carrier-API experimentation surface |
| Open Gateway SIM Swap — https://opengateway.telefonica.com/apis/sim-swap | Telecom-grade anti-fraud signal |

## Discovery caveat

- ClaimReview interoperability still matters, but Google Search is phasing out some fact-check rich-result treatment. Use ClaimReview for exchange and retrieval, not as the core discovery moat.
- Google Business Messages should not be treated as a live future rail. Google's own docs say the product was wound down on 2024-07-31.

## Threat-intel feeds

| Source | Use |
|---|---|
| URLhaus — https://urlhaus.abuse.ch/api/ | Malicious URL feed |
| ThreatFox — https://threatfox.abuse.ch/api/ | IOC feed |
| OpenPhish — https://www.openphish.com/phishing_feeds.html | Phishing indicators |
| PhishTank — https://www.phishtank.org/ | Community phishing data |

## Product law for ingestion

- Official sources outrank third-party feeds.
- Fact checking must not be merged with scam scoring as though they are the same task.
- Community or third-party reports must never become verdicts without language that keeps them probabilistic.
- Threat feeds should be cacheable and reviewable, not blindly executed into blocklists.
