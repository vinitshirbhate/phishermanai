from __future__ import annotations

from typing import Any


OFFICIAL_RECOVERY_RAILS: list[dict[str, Any]] = [
    {
        "id": "ncrp_1930",
        "name": "National Cyber Crime Portal / 1930",
        "kind": "loss_or_live_financial_fraud",
        "country": "India",
        "url": "https://www.cybercrime.gov.in/",
        "hotline": "1930",
        "use_when": "Use immediately when money is already at risk, money has been lost, or account compromise is ongoing.",
        "channels": ["call", "sms", "whatsapp", "telegram", "email", "website", "upi", "social"],
        "source": "https://www.cybercrime.gov.in/",
    },
    {
        "id": "chakshu",
        "name": "Chakshu / Sanchar Saathi",
        "kind": "suspected_fraud_communication",
        "country": "India",
        "url": "https://www.sancharsaathi.gov.in/sfc/",
        "use_when": "Use for suspicious calls, SMS, WhatsApp messages, or malicious links received within the last 30 days when money has not yet been lost.",
        "channels": ["call", "sms", "whatsapp", "website", "url"],
        "source": "https://www.sancharsaathi.gov.in/sfc/",
    },
    {
        "id": "i4c_suspect_repository",
        "name": "I4C Suspect Repository Search",
        "kind": "indicator_lookup",
        "country": "India",
        "url": "https://cybercrime.gov.in/Webform/suspect_search_repository.aspx",
        "use_when": "Search a phone number, UPI ID, URL, wallet, or account identifier before acting or while preparing a case packet.",
        "channels": ["call", "sms", "whatsapp", "telegram", "email", "website", "upi", "social"],
        "source": "https://i4c.mha.gov.in/",
    },
    {
        "id": "npci_upi_awareness",
        "name": "NPCI UPI Safety Guidance",
        "kind": "payment_safety_reference",
        "country": "India",
        "url": "https://www.npci.org.in/what-we-do/upi/cyber-awareness",
        "use_when": "Use for UPI collect requests, QR-code payment tricks, fake payment proofs, and payment-approval pressure.",
        "channels": ["upi", "website", "whatsapp", "sms"],
        "source": "https://www.npci.org.in/what-we-do/upi/cyber-awareness",
    },
    {
        "id": "rbi_cms",
        "name": "RBI Complaint Management System",
        "kind": "banking_redress_after_initial_complaint",
        "country": "India",
        "url": "https://cms.rbi.org.in/",
        "use_when": "Use after raising the issue with the bank, card issuer, wallet, or payment participant if the response is delayed, inadequate, or unresolved.",
        "channels": ["banking", "upi", "card", "wallet", "website"],
        "source": "https://www.rbi.org.in/Scripts/SMSCMS.aspx",
    },
    {
        "id": "pib_fact_check",
        "name": "PIB Fact Check",
        "kind": "government_claim_verification",
        "country": "India",
        "url": "https://pib.gov.in/aboutfactchecke.aspx",
        "use_when": "Use when a message or media asset claims to quote the Government of India or a public agency.",
        "channels": ["social", "website", "whatsapp", "telegram", "email"],
        "source": "https://pib.gov.in/aboutfactchecke.aspx",
    },
    {
        "id": "google_fact_check_tools",
        "name": "Google Fact Check Tools API",
        "kind": "claim_review_lookup",
        "country": "Global",
        "url": "https://developers.google.com/fact-check/tools/api/",
        "use_when": "Use to search existing fact checks and claim-review records for public claims, misinformation, or reused narratives.",
        "channels": ["website", "social", "whatsapp", "telegram", "email"],
        "source": "https://developers.google.com/fact-check/tools/api/",
    },
]

CHANNEL_TRUST_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "whatsapp_meta_verified",
        "name": "WhatsApp Meta Verified",
        "surface": "whatsapp",
        "signal": "Verified business badge with impersonation protection",
        "use_for": "Treat as one channel-trust signal for business identity, never as a final safety verdict.",
        "source": "https://about.fb.com/news/2024/06/new-ai-tools-meta-verified-and-more-for-businesses-on-whatsapp/",
    },
    {
        "id": "truecaller_secure_call",
        "name": "Truecaller Secure Call",
        "surface": "phone_call",
        "signal": "Real-time backend authentication and secure-call badge",
        "use_for": "Model enterprise call verification for banks, support desks, and high-risk merchants.",
        "source": "https://docs.truecaller.com/truecaller-for-business/features/secure-calls/how-does-secure-call-work",
    },
    {
        "id": "monzo_call_status",
        "name": "In-app Call Status",
        "surface": "banking_app",
        "signal": "Customer checks in-app whether the brand is actually on the call",
        "use_for": "Strong product pattern for bank/fintech anti-impersonation flows.",
        "source": "https://monzo.com/help/monzo-fraud-category/monzo-call-status-web",
    },
    {
        "id": "google_rcs_for_business",
        "name": "RCS for Business",
        "surface": "carrier_messaging",
        "signal": "Carrier-grade branded messaging with rich cards and reachability controls",
        "use_for": "Merchant and BFSI messaging surfaces where SMS fallback still matters.",
        "source": "https://developers.google.com/business-communications/rcs-business-messaging/guides/get-started/how-it-works",
    },
]

PROVENANCE_STACK: list[dict[str, Any]] = [
    {
        "id": "c2pa_spec",
        "name": "C2PA Content Credentials Spec",
        "role": "provenance_standard",
        "why_it_matters": "Lets Phisherman AI verify origin and edit history when credentials are present instead of pretending deepfake detection is solved.",
        "source": "https://c2pa.org/",
    },
    {
        "id": "c2pa_conformance",
        "name": "C2PA Conformance and Trust List",
        "role": "validator_and_trust_program",
        "why_it_matters": "Makes validator outputs more trustworthy than ad-hoc provenance claims.",
        "source": "https://c2pa.org/conformance/",
    },
    {
        "id": "contentauth_c2pa_rs",
        "name": "Content Authenticity C2PA Rust SDK",
        "role": "verification_sdk",
        "why_it_matters": "Open-source SDK path for a local verifier or service wrapper.",
        "source": "https://github.com/contentauth/c2pa-rs",
    },
    {
        "id": "contentauth_c2pa_android",
        "name": "Content Authenticity C2PA Android SDK",
        "role": "mobile_sdk",
        "why_it_matters": "Path to native provenance checks if Phisherman AI moves onto Android.",
        "source": "https://github.com/contentauth/c2pa-android",
    },
]

LEVERAGE_MAP: list[dict[str, Any]] = [
    {
        "id": "recovery_rails",
        "name": "Recovery Rails",
        "stage": "build_now",
        "why_now": "The product should not stop at detection. India already exposes official reporting and suspect-search rails that can be converted into a recovery packet.",
        "build_now": [
            "Generate structured case packets from scans.",
            "Route users to Chakshu, NCRP/1930, I4C suspect search, and NPCI safety references.",
            "Keep official reporting separate from risk scoring."
        ],
        "v3_path": "Turn case packets into operator review queues, evidence replay, and partner-ready recovery APIs.",
        "sources": [
            "https://www.sancharsaathi.gov.in/sfc/",
            "https://www.cybercrime.gov.in/",
            "https://i4c.mha.gov.in/",
            "https://www.npci.org.in/what-we-do/upi/cyber-awareness",
        ],
    },
    {
        "id": "channel_identity",
        "name": "Channel Identity",
        "stage": "build_now",
        "why_now": "Fraud is often a channel-trust problem before it is a content-trust problem.",
        "build_now": [
            "Model verified-call and verified-business patterns as first-class product signals.",
            "Separate verified channel, verified sender, and verified content as different truths."
        ],
        "v3_path": "Integrate verified-call, verified-business, and in-app callback rails without collapsing them into content truth.",
        "sources": [
            "https://about.fb.com/news/2024/06/new-ai-tools-meta-verified-and-more-for-businesses-on-whatsapp/",
            "https://docs.truecaller.com/truecaller-for-business/features/secure-calls/how-does-secure-call-work",
            "https://monzo.com/help/monzo-fraud-category/monzo-call-status-web",
            "https://developers.google.com/business-communications/rcs-business-messaging/guides/get-started/how-it-works",
        ],
    },
    {
        "id": "device_and_app_trust",
        "name": "Device and App Trust",
        "stage": "build_now",
        "why_now": "High-risk guidance should only come from trusted app surfaces, not clones or tampered builds.",
        "build_now": [
            "Use Play Integrity for official Android builds.",
            "Use system-backed key verification for end-to-end trust workflows."
        ],
        "v3_path": "Bind recovery, guardian flows, and evidence sharing to attested app sessions.",
        "sources": [
            "https://developer.android.com/google/play/integrity",
            "https://developer.android.com/privacy-and-security/key-verifier",
        ],
    },
    {
        "id": "network_signals",
        "name": "Network Signals",
        "stage": "design_now",
        "why_now": "Carrier-grade number verification, SIM-swap, and device status APIs are becoming productizable anti-fraud primitives.",
        "build_now": [
            "Design the policy layer and request schemas now.",
            "Keep the sandbox integration abstract until a carrier or aggregator path is chosen."
        ],
        "v3_path": "Integrate Number Verification, SIM Swap, KYC Match, and Device Status with explicit consent and policy gates.",
        "sources": [
            "https://opengateway.telefonica.com/apis/sim-swap",
            "https://developers.opengateway.telefonica.com/docs/sandbox",
        ],
    },
    {
        "id": "provenance_not_deepfake",
        "name": "Provenance, Not Deepfake Theater",
        "stage": "build_now",
        "why_now": "C2PA and Content Credentials are mature enough to support a real provenance lane, while still preserving 'unverified' as a safe outcome.",
        "build_now": [
            "Expose provenance-present, provenance-missing, and provenance-invalid as separate states.",
            "Never treat missing credentials as proof of deception."
        ],
        "v3_path": "Local and mobile verifiers, signed case packets, and source-chain replay.",
        "sources": [
            "https://c2pa.org/",
            "https://c2pa.org/conformance/",
            "https://github.com/contentauth/c2pa-rs",
            "https://github.com/contentauth/c2pa-android",
        ],
    },
    {
        "id": "telegram_mini_app",
        "name": "Telegram Mini App",
        "stage": "build_now",
        "why_now": "Telegram Mini Apps now support secure local storage and can graduate MirrorMesh Lite from command bot to real interface.",
        "build_now": [
            "Use bot plus Mini App, not bot alone.",
            "Treat secure local storage as a state cache, not a secrets vault for irreversible actions."
        ],
        "v3_path": "Consumer and merchant triage surfaces with replayable state, evidence packet handoff, and guardian flows.",
        "sources": [
            "https://core.telegram.org/bots/webapps",
        ],
    },
    {
        "id": "factcheck_distribution_shift",
        "name": "Fact-check Distribution Shift",
        "stage": "build_now",
        "why_now": "ClaimReview interoperability still matters, but Google is phasing out some structured-data visibility surfaces. Discovery cannot depend on Search rich results.",
        "build_now": [
            "Keep ClaimReview for interoperability and the Fact Check tools ecosystem.",
            "Do not assume Search result treatment is the moat.",
            "Invest in direct product surfaces, feeds, and operator tools instead."
        ],
        "v3_path": "Own discovery through Phisherman AI surfaces, partner channels, and signed evidence sharing.",
        "sources": [
            "https://developers.google.com/fact-check/tools/api/",
            "https://developers.google.com/search/updates",
            "https://developers.google.com/search/blog/2025/11/update-on-our-efforts",
        ],
    },
]


def classify_incident(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("upi", "collect request", "scan qr", "payment proof", "pay now")):
        return "payment_fraud"
    if any(token in lower for token in ("kyc", "account suspended", "wallet", "bank account", "otp")):
        return "account_takeover_or_payment_phish"
    if any(token in lower for token in ("deepfake", "breaking news", "viral", "government notice", "fact check")):
        return "claim_or_media_verification"
    return "suspicious_communication"


def recovery_rails_for(
    channel: str,
    incident_type: str,
    lost_money: bool,
    has_url: bool,
    bank_contacted: bool = False,
    unresolved_with_bank: bool = False,
) -> list[dict[str, Any]]:
    selected: list[str] = []
    if lost_money:
        selected.append("ncrp_1930")
    if channel in {"call", "sms", "whatsapp", "website", "url"} or has_url:
        selected.append("chakshu")
    selected.append("i4c_suspect_repository")
    if incident_type == "payment_fraud":
        selected.append("npci_upi_awareness")
    if bank_contacted and (unresolved_with_bank or lost_money):
        selected.append("rbi_cms")
    if incident_type == "claim_or_media_verification":
        selected.extend(["pib_fact_check", "google_fact_check_tools"])

    seen: set[str] = set()
    rails: list[dict[str, Any]] = []
    for rail in OFFICIAL_RECOVERY_RAILS:
        if rail["id"] in selected and rail["id"] not in seen:
            seen.add(rail["id"])
            rails.append(dict(rail))
    return rails


def immediate_steps_for(incident_type: str, lost_money: bool) -> list[str]:
    steps: list[str] = [
        "Pause the interaction. Do not send OTPs, UPI approvals, passwords, or card details.",
        "Capture screenshots, sender details, URLs, phone numbers, and timestamps before the content disappears.",
    ]
    if incident_type in {"payment_fraud", "account_takeover_or_payment_phish"}:
        steps.append("Verify the request from the official app, official website, or a trusted callback path before doing anything else.")
    if lost_money:
        steps.append("Escalate immediately to the National Cyber Crime Portal or call 1930 while the transaction trail is still fresh.")
    else:
        steps.append("If this is a suspected fraud communication and no money is lost yet, report it through Chakshu.")
    return steps


def evidence_checklist_for(channel: str) -> list[str]:
    checklist = [
        "Timestamp of the interaction",
        "Exact message text or page text",
        "Sender phone number, handle, or domain",
        "Screenshots of the suspicious content",
    ]
    if channel in {"website", "url"}:
        checklist.append("Full URL and any redirected destination")
    if channel in {"call", "sms", "whatsapp", "telegram"}:
        checklist.append("Call log or chat thread showing the sender")
    checklist.append("Any extracted UPI ID, account hint, QR code, or payment instructions")
    return checklist


def support_script_for(
    mode: str,
    language: str,
    incident_type: str,
    lost_money: bool,
    claimed_brand: str,
    rails: list[dict[str, Any]],
) -> dict[str, Any]:
    lang = "hi" if language == "hi" else "en"
    brand = claimed_brand or "the claimed sender"
    first_rail = rails[0]["name"] if rails else "the official reporting rail"
    second_rail = rails[1]["name"] if len(rails) > 1 else ""

    fact_line = {
        "payment_fraud": f"This appears to involve payment pressure or a UPI-style fraud flow linked to {brand}.",
        "account_takeover_or_payment_phish": f"This appears to involve credential theft or account compromise linked to {brand}.",
        "claim_or_media_verification": f"This appears to involve a public claim or media item presented as if it came from {brand}.",
    }.get(incident_type, f"This appears to involve a suspicious communication linked to {brand}.")

    ask_line = (
        f"I want the safest official next step, starting with {first_rail}."
        if not second_rail
        else f"I want the safest official next step, starting with {first_rail} and then {second_rail} if needed."
    )
    if lost_money:
        ask_line = f"Money may already be lost. I want the fastest official next step, starting with {first_rail}."

    if mode == "merchant":
        fact_line = f"This looks like fake payment confirmation pressure tied to {brand}. I need to hold fulfilment until money is verified in the official app."
    elif mode == "guardian":
        fact_line = f"A family member may act on a panic forward linked to {brand}. I need to slow the interaction down and verify it through an official path."
    elif mode == "operator":
        fact_line = f"I am preparing an operator triage packet for a case linked to {brand}. I need the official escalation order, not generic advice."

    if lang == "hi":
        fact_line = {
            "payment_fraud": f"Yeh payment pressure ya UPI fraud jaisa case lag raha hai, jo {brand} se juda hua dikh raha hai.",
            "account_takeover_or_payment_phish": f"Yeh credential theft ya account compromise jaisa case lag raha hai, jo {brand} se juda hua dikh raha hai.",
            "claim_or_media_verification": f"Yeh public claim ya media verification ka case lag raha hai, jo {brand} ke naam se circulate ho raha hai.",
        }.get(incident_type, f"Yeh suspicious communication ka case lag raha hai, jo {brand} se juda hua dikh raha hai.")
        ask_line = (
            f"Mujhe sabse sahi official next step chahiye, pehle {first_rail} ke through."
            if not second_rail
            else f"Mujhe sabse sahi official next step chahiye, pehle {first_rail} aur zarurat pade to {second_rail} ke through."
        )
        if lost_money:
            ask_line = f"Paisa shayad ja chuka hai. Mujhe sabse tez official next step chahiye, pehle {first_rail} ke through."
        if mode == "merchant":
            fact_line = f"Yeh fake payment proof pressure lag raha hai jo {brand} se juda hua dikh raha hai. Official app me paise confirm hone tak mujhe order hold rakhna hai."
        elif mode == "guardian":
            fact_line = f"Ghar ka koi vyakti {brand} ke naam par aayi panic forward par action le sakta hai. Mujhe is interaction ko rok kar official tareeke se verify karna hai."
        elif mode == "operator":
            fact_line = f"Main {brand} se jude case ka operator triage packet bana raha hoon. Mujhe generic advice nahi, official escalation order chahiye."

    opening = (
        "I need help with a suspected scam case and I want to stay on official rails only."
        if lang == "en"
        else "Mujhe suspected scam case me madad chahiye aur mujhe sirf official rails par rehna hai."
    )
    close = (
        "Please tell me the exact reporting or escalation path I should follow next."
        if lang == "en"
        else "Kripya mujhe exact reporting ya escalation path bataye jo mujhe ab follow karna chahiye."
    )
    facts = [
        fact_line,
        "I have screenshots, identifiers, and timestamps ready."
        if lang == "en"
        else "Mere paas screenshots, identifiers aur timestamps ready hain.",
    ]
    copy_text = "\n".join([opening, fact_line, ask_line, close])
    return {
        "language": lang,
        "opening": opening,
        "facts": facts,
        "ask": ask_line,
        "close": close,
        "copy_text": copy_text,
    }
