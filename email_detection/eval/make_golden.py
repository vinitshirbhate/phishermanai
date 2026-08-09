"""Build the golden corpus: genuine Indian financial communications that must
NEVER be flagged.

    python -m eval.make_golden

This is the regression harness the precision-first refactor is measured
against. Every sample is a real-shaped communication from a depository, bank,
broker, RTA, AMC or regulator, deliberately dense with the vocabulary a naive
rule set reads as hostile:

    click here / login / password / verify / urgent / last date / PAN /
    register / account / OTP / block / suspend / KYC / deadline / immediate

Any rule that fires here is direction-blind and must be fixed or deleted.

The corpus includes forwarded copies -- inline AND as attachments -- because
forwarding is how users actually submit mail, and the forwarder must never be
analysed as the sender.
"""

from __future__ import annotations

import email
import email.policy
import json
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
BASE_DATE = datetime(2026, 8, 3, 10, 30)


def _auth(domain: str) -> str:
    return (f"mx.google.com; dkim=pass header.i=@{domain} header.s=s1; "
            f"spf=pass smtp.mailfrom=noreply@{domain}; "
            f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={domain}")


# (set, sender_name, sender_addr, subject, body)
SAMPLES: list[tuple[str, str, str, str, str]] = []


def add(group, name, addr, subject, body):
    SAMPLES.append((group, name, addr, subject, body))


# ---------------------------------------------------------- DEPOSITORY (20)
for i, (dp, addr, extra) in enumerate([
    ("CDSL e-Voting", "helpdesk.evoting@cdslindia.com",
     "The system will authenticate the user by sending OTP on registered Mobile & Email as "
     "recorded in the Demat Account. BO ID 1209870000018454."),
    ("NSDL e-Voting", "evoting@nsdl.com",
     "A One Time Password will be sent to your registered mobile number for verification. "
     "Your User ID is your 8 character DP ID followed by 8 digit Client ID. IN30021412345678."),
    ("CDSL Easi", "easi@cdslindia.com",
     "Click here to login to Easi with your existing user id and password. If you are not "
     "registered, the option to register is available on the home page."),
    ("NSDL IDeAS", "ideas@nsdl.com",
     "Login with your user ID and password to view holdings across your demat accounts. "
     "NSDL will never call or email you asking for your password or OTP."),
    ("CDSL Transaction", "statements@cdslindia.com",
     "Your transaction statement is attached. The password for this statement is your PAN "
     "in upper case. PAN ABCDE1234F."),
], start=1):
    for variant in range(4):
        subjects = [
            "Remote e-Voting instructions for shareholders",
            "Notice: e-Voting for AGM 2026 - last date to cast your vote is 11 August 2026",
            "Your demat account statement for July 2026",
            "Important: verify your account details as per SEBI circular",
        ]
        add("depository", dp, addr, subjects[variant],
            f"""Dear Demat Account Holder,

As per SEBI circular no. SEBI/HO/CFD/CMD/CIR/P/2026/{40 + i}, please note the following.

{extra}

Holdings: ANANT RAJ -EQ RS 2 ISIN INE242C01024, RELIANCE -EQ RS 10 ISIN INE002A01018.
Folio No. ANR000{i}234. DP ID 12098700.

Kindly verify your account details and update your PAN and bank mandate with your
Depository Participant. Folios without PAN and nomination are liable to be frozen.

Toll free 1800 22 55 33. Please report any suspicious message to us immediately.

{dp}
""")

# ------------------------------------------------------- BANK STATEMENTS (15)
for i in range(15):
    banks = [("State Bank of India", "alerts@sbi.co.in"), ("HDFC Bank", "alerts@hdfcbank.com"),
             ("ICICI Bank", "statements@icicibank.com"), ("Axis Bank", "alerts@axisbank.com"),
             ("Canara Bank", "alerts@canarabank.com")]
    bank, addr = banks[i % len(banks)]
    add("bank", bank, addr,
        f"Your account statement for July 2026 - {bank}",
        f"""Dear Customer,

Your account statement is attached. The password to open this statement is your PAN in
upper case followed by your date of birth in DDMM format.

An OTP will be sent to your registered mobile number when you log in to net banking.
{bank} will never ask you for your OTP, PIN, CVV or password. If anyone asks you to
share these, please report it to us immediately on 1800 11 2211.

To update your KYC, please visit your nearest branch or log in to net banking. Accounts
with incomplete KYC may be restricted as per RBI guidelines.

This is a system generated email. Please do not reply to this message.

{bank}
""")

# ------------------------------------------------------------- BROKERS (20)
for i in range(20):
    brokers = [("Zerodha", "support@zerodha.com", "INZ000031633"),
               ("Angel One", "support@angelone.in", "INZ000161534"),
               ("Upstox", "support@upstox.com", "INZ000315837"),
               ("Kotak Securities", "service.securities@kotak.com", "INZ000200137"),
               ("HDFC Securities", "customercare@hdfcsec.com", "INZ000186937")]
    broker, addr, reg = brokers[i % len(brokers)]
    kinds = [
        ("Contract note for trades dated 03 August 2026",
         "Please find attached the digitally signed contract note. The attachment is password "
         "protected; the password is your PAN in upper case."),
        ("Margin shortfall in your trading account",
         "Your account has a margin shortfall of Rs 12,450. Please add funds or reduce positions "
         "before the market opens to avoid square-off as per exchange rules."),
        ("Re-KYC required for your trading and demat account",
         "As per SEBI regulations your KYC is due for revalidation. Please complete re-KYC at your "
         "convenience by logging in to your account. If not completed, your account may be "
         "restricted for new positions."),
        ("Your ledger and holdings statement for July 2026",
         "Your ledger statement is attached. You can also view holdings by logging in with your "
         "Client ID and password."),
    ]
    subject, detail = kinds[i % len(kinds)]
    add("broker", broker, addr, subject,
        f"""Dear Client,

{detail}

We will never ask you for your password, OTP or PIN over a call or message. Do not share
your login credentials with anyone, including persons claiming to be from our support team.

For any grievance write to us, or escalate to SEBI SCORES at https://scores.sebi.gov.in

{broker}
SEBI Registration: {reg}
""")

# ------------------------------------------------- RTA / CORPORATE ACTIONS (20)
for i in range(20):
    rtas = [("KFin Technologies", "einward.ris@kfintech.com"),
            ("MUFG Intime India", "investor.helpdesk@linkintime.co.in"),
            ("CAMS", "camsCAS@camsonline.com"),
            ("Bigshare Services", "investor@bigshareonline.com")]
    rta, addr = rtas[i % len(rtas)]
    kinds = [
        ("Intimation of record date for payment of final dividend",
         "The Record Date has been fixed as Friday, 21 August 2026. The dividend will be credited "
         "directly to the bank account registered with your Depository Participant. No action or "
         "payment is required from you."),
        ("Notice of 42nd Annual General Meeting and e-Voting information",
         "The remote e-Voting period commences on 22 August 2026 and ends on 24 August 2026. The "
         "last date to cast your vote is 24 August 2026."),
        ("Unclaimed dividend liable to be transferred to IEPF",
         "Pursuant to Sections 124 and 125 of the Companies Act 2013, dividends unclaimed for seven "
         "years must be transferred to the Investor Education and Protection Fund. To claim, submit "
         "Form IEPF-5. No fee is payable to the Company or the Registrar."),
        ("Nomination and PAN update required for your folio",
         "As per SEBI circular, folios without PAN, nomination or bank mandate are liable to be "
         "frozen. Please submit Form ISR-1 with self-attested PAN. There is no fee for this service."),
        ("Rights issue - application form and ASBA instructions",
         "You may apply through ASBA by submitting the application to your Self Certified Syndicate "
         "Bank. Do not make any payment to any individual; application money is blocked in your own "
         "bank account and debited only on allotment."),
    ]
    subject, detail = kinds[i % len(kinds)]
    add("rta", rta, addr, subject,
        f"""Dear Shareholder,

{detail}

Folio No. ANR00{i:02d}45. DP ID 12098700. Client ID 00018454.

For queries please contact the Registrar and Share Transfer Agent.

{rta}
""")

# ------------------------------------------------------- MUTUAL FUNDS (15)
for i in range(15):
    amcs = [("SBI Mutual Fund", "customer.delight@sbimf.com"),
            ("HDFC Mutual Fund", "service@hdfcfund.com"),
            ("ICICI Prudential MF", "enquiry@icicipruamc.com"),
            ("Nippon India MF", "customercare@nipponindiamf.com"),
            ("Axis Mutual Fund", "service@axismf.com")]
    amc, addr = amcs[i % len(amcs)]
    kinds = [
        ("Your SIP instalment is due on 10 August 2026",
         "Your SIP instalment of Rs 5,000 will be debited on 10 August 2026. Please approve the UPI "
         "mandate request in your UPI application when it arrives."),
        ("Redemption request processed",
         "Your redemption request has been processed. The amount will be credited to your registered "
         "bank account within 3 working days."),
        ("Consolidated Account Statement for July 2026",
         "Your CAS is attached. The statement is password protected; your password is your PAN in "
         "upper case. An OTP will be sent to your registered mobile for online access."),
    ]
    subject, detail = kinds[i % len(kinds)]
    add("mutual_fund", amc, addr, subject,
        f"""Dear Investor,

{detail}

Folio No. {10000000 + i}. PAN ABCDE1234F.

Mutual fund investments are subject to market risks. Read all scheme related documents
carefully before investing. Past performance is not indicative of future results. There is
no assurance or guarantee of returns.

{amc}
""")

# --------------------------------------------------- KYC / REGULATORY (10)
for i in range(10):
    add("regulatory", "SEBI Investor Assistance", "investorassistance@sebi.gov.in",
        f"Investor Charter and grievance redressal - notice {i+1}",
        f"""Dear Investor,

In accordance with SEBI circular no. SEBI/HO/OIAE/IGRD/P/CIR/2026/{i+10}, we are sharing
the Investor Charter setting out your rights.

If you have a grievance, lodge a complaint on SCORES at https://scores.sebi.gov.in or
through the SMART ODR portal at https://smartodr.in

Beware of fraudsters. SEBI never asks investors for money, and never guarantees returns on
any investment. Do not share your login credentials, OTP or PIN with anyone.

Please verify the registration of any intermediary before investing.

Securities and Exchange Board of India
""")


def _build_message(group, name, addr, subject, body, index) -> EmailMessage:
    domain = addr.split("@")[-1]
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Date"] = format_datetime(BASE_DATE - timedelta(hours=index * 3))
    msg["From"] = f"{name} <{addr}>"
    msg["To"] = "investor@example.com"
    msg["Subject"] = subject
    msg["Return-Path"] = f"<bounce@{domain}>"
    msg["Authentication-Results"] = _auth(domain)
    msg["Received"] = (f"from mail.{domain} (mail.{domain} [203.0.113.20]) by mx.google.com "
                       f"with ESMTPS id g{index}; {format_datetime(BASE_DATE)}")
    msg.set_content(body)
    return msg


def _forward_inline(original: EmailMessage, forwarder="shourya@gmail.com") -> EmailMessage:
    """A Gmail-style inline forward: original headers quoted into the body."""
    fwd = EmailMessage()
    fwd["Message-ID"] = make_msgid(domain="gmail.com")
    fwd["Date"] = format_datetime(BASE_DATE)
    fwd["From"] = f"Investor <{forwarder}>"
    fwd["To"] = "check@phishermanai.local"
    fwd["Subject"] = f"Fwd: {original['Subject']}"
    fwd["Authentication-Results"] = _auth("gmail.com")
    fwd.set_content(
        "Is this genuine? Please check.\n\n"
        "---------- Forwarded message ----------\n"
        f"From: {original['From']}\n"
        f"Date: {original['Date']}\n"
        f"Subject: {original['Subject']}\n"
        f"To: {original['To']}\n\n"
        f"{original.get_content()}"
    )
    return fwd


def _forward_attached(original: EmailMessage, forwarder="shourya@gmail.com") -> EmailMessage:
    fwd = EmailMessage()
    fwd["Message-ID"] = make_msgid(domain="gmail.com")
    fwd["Date"] = format_datetime(BASE_DATE)
    fwd["From"] = f"Investor <{forwarder}>"
    fwd["To"] = "check@phishermanai.local"
    fwd["Subject"] = f"Fwd: {original['Subject']}"
    fwd["Authentication-Results"] = _auth("gmail.com")
    fwd.set_content("Attaching the original for you to check.")
    fwd.add_attachment(original)
    return fwd


def build() -> dict:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for stale in GOLDEN_DIR.glob("*.eml"):
        stale.unlink()

    manifest = []
    built: list[EmailMessage] = []

    for index, (group, name, addr, subject, body) in enumerate(SAMPLES):
        msg = _build_message(group, name, addr, subject, body, index)
        built.append(msg)
        filename = f"g_{group}_{index:03d}.eml"
        (GOLDEN_DIR / filename).write_bytes(msg.as_bytes())
        manifest.append({"file": filename, "set": group, "sender": addr,
                         "subject": subject, "forward_type": "DIRECT"})

    # 10 inline forwards and 10 attached forwards, spread across the sets.
    step = max(1, len(built) // 10)
    for n, msg in enumerate(built[::step][:10]):
        fwd = _forward_inline(msg)
        filename = f"g_fwd_inline_{n:03d}.eml"
        (GOLDEN_DIR / filename).write_bytes(fwd.as_bytes())
        manifest.append({"file": filename, "set": "forwarded_inline",
                         "sender": msg["From"], "subject": str(fwd["Subject"]),
                         "forward_type": "INLINE"})

    for n, msg in enumerate(built[1::step][:10]):
        fwd = _forward_attached(msg)
        filename = f"g_fwd_attached_{n:03d}.eml"
        (GOLDEN_DIR / filename).write_bytes(fwd.as_bytes())
        manifest.append({"file": filename, "set": "forwarded_attached",
                         "sender": msg["From"], "subject": str(fwd["Subject"]),
                         "forward_type": "ATTACHED"})

    (GOLDEN_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for item in manifest:
        counts[item["set"]] = counts.get(item["set"], 0) + 1
    return {"total": len(manifest), "by_set": counts, "dir": str(GOLDEN_DIR)}


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(build(), indent=2))
