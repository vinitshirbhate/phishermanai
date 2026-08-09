"""Adversarial golden set: genuine mail whose SUBJECT MATTER is fraud.

    python -m eval.make_adversarial

These are the hardest possible inputs for a rule engine. Investor-awareness
material from exchanges, regulators and brokers exists precisely to describe
fraud, so it is dense with every phrase a detector looks for:

    "guaranteed returns"   "assured profit"    "Ponzi scheme"
    "share your OTP"       "digital arrest"    "double your money"
    "pre-IPO allotment"    "unclaimed dividend"

A keyword system scores these as fraud with total confidence. That already
happened: an NSE awareness email warning that "no one can promise guaranteed
returns" was scored FRAUDULENT.

Each set is generated in two variants so BOTH code paths are tested:

  DIRECT     from the authorised domain with valid DKIM -> should short-circuit
  FORWARDED  inline-forwarded from Gmail, so the original signature is gone and
             the CONTENT RULES must handle it unaided

The forwarded variants are the real test. Without them the corpus would only
prove the short-circuit works, not that the rules stopped misfiring.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "golden" / "adversarial"
BASE_DATE = datetime(2026, 8, 5, 9, 0)


def _auth(domain: str, *, dkim="pass", dmarc="pass") -> str:
    return (f"mx.google.com; dkim={dkim} header.i=@{domain} header.s=s1; "
            f"spf=pass smtp.mailfrom=noreply@{domain}; "
            f"dmarc={dmarc} (p=REJECT) header.from={domain}")


# ---------------------------------------------------------------------------
# 1. NSE / BSE investor awareness (15)
# ---------------------------------------------------------------------------
EXCHANGE_AWARENESS = [
    ("Beware of assured return schemes",
     """Dear Investor,

NSE cautions investors against entities promising assured or guaranteed returns.
NO ONE can promise you a guaranteed or regular return on your investment in the
securities market. Returns are subject to market risk.

Any person offering you a fixed monthly income from share trading is acting in
violation of SEBI regulations. Do not be misled.

Call our toll free helpline 1800 266 0050."""),
    ("Do not share your trading credentials",
     """Dear Investor,

Fraudsters may call you claiming to be from the exchange and ask you to share
your OTP, PIN or trading password. Never share these with anyone. The exchange
will never ask you for your OTP or password.

Do not install any screen-sharing application such as AnyDesk at the request of
a caller. Report such calls on our toll free number 1800 266 0050."""),
    ("Caution against unsolicited investment tips",
     """Dear Investor,

Investors are cautioned against unsolicited stock tips circulated through
WhatsApp and Telegram groups promising multibagger returns. Such groups often
claim to have insider information. Acting on insider information is a criminal
offence under the SEBI (Prohibition of Insider Trading) Regulations, 2015.

Deal only with SEBI registered intermediaries."""),
    ("Beware of fake trading applications",
     """Dear Investor,

Fraudulent trading applications are being distributed outside the Play Store as
APK files. These applications display fabricated profits and then demand a tax
or processing fee before allowing withdrawal. No genuine broker asks you to pay
a fee to withdraw your own money.

Download applications only from official app stores."""),
    ("Caution: pre-IPO and unlisted share offers",
     """Dear Investor,

Investors are cautioned against offers of guaranteed pre-IPO allotment or
exclusive unlisted shares. IPO allotment in an oversubscribed issue is decided
by a computerised lottery run by the registrar. Nobody can guarantee you an
allotment.

Application money under ASBA is blocked in your own bank account."""),
]

# ---------------------------------------------------------------------------
# 2. SEBI investor education (10)
# ---------------------------------------------------------------------------
SEBI_EDUCATION = [
    ("Investor education: recognising Ponzi schemes",
     """Dear Investor,

A Ponzi scheme pays existing investors from money contributed by new investors
rather than from genuine profit. Warning signs include a promise to double your
money, a fixed monthly return, and pressure to recruit others.

SEBI never approves, certifies or guarantees any investment scheme or its
returns. Any claim that SEBI backs a return is false.

Lodge complaints on SCORES at https://scores.sebi.gov.in"""),
    ("Investor education: digital arrest and impersonation",
     """Dear Investor,

There is no procedure in Indian law called a digital arrest. Fraudsters
impersonating regulators or police may claim your demat account is frozen in a
money laundering case and demand an immediate payment to settle it.

SEBI never contacts individual investors to demand payment of any fine or
penalty. Disconnect such calls and report them."""),
    ("Investor education: unclaimed dividend and IEPF",
     """Dear Investor,

Dividends unclaimed for seven consecutive years are transferred to the Investor
Education and Protection Fund under Sections 124 and 125 of the Companies Act,
2013. Claims are made by filing Form IEPF-5 through the MCA portal.

No fee is payable to any agent. Beware of messages asking you to click a link
and pay a verification charge to release an unclaimed dividend."""),
    ("Investor education: verify before you invest",
     """Dear Investor,

Before investing, verify the registration of the intermediary. Registered
intermediaries collecting investor funds must use a validated UPI address ending
in .brk@valid for brokers or .mf@valid for mutual funds.

Never transfer investment money to a personal UPI handle or an individual's bank
account, however convincing the request appears."""),
    ("Investor education: KYC and account freezing",
     """Dear Investor,

As per SEBI circular, folios without PAN, nomination or a valid bank mandate are
liable to be frozen. This is a regulatory requirement, not a penalty, and no fee
is payable to unfreeze a folio.

Update your details only through your Depository Participant or the Registrar
and Transfer Agent, never through a link received in a message."""),
]

# ---------------------------------------------------------------------------
# 3. Broker fraud-warning advisories (10)
# ---------------------------------------------------------------------------
BROKER_ADVISORIES = [
    ("Security advisory: we will never ask for your OTP",
     """Dear Client,

We will never ask you to share your OTP, PIN, CVV or password, and we will never
ask you to install a remote access application. Anyone who does is attempting to
take money from your account.

If you receive such a call, disconnect and report it to us immediately."""),
    ("Advisory: beware of guaranteed return offers in our name",
     """Dear Client,

Some entities are using our name to offer guaranteed monthly returns and VIP
tip groups in exchange for a membership fee. We do not operate any such group
and we do not promise assured returns on any product.

Equity investment is subject to market risk. We never guarantee returns."""),
    ("Advisory: fake withdrawal fee demands",
     """Dear Client,

Clients have reported messages claiming a withdrawal is blocked until a
clearance fee is paid. This is a fraud. Withdrawals from your trading account
are credited to your registered bank account as per the settlement cycle, and no
fee is ever collected separately to release them."""),
    ("Advisory: mule accounts and commission offers",
     """Dear Client,

Do not allow anyone to route money through your bank account in exchange for a
commission. Doing so makes you a mule account holder, which is a criminal
offence under the PMLA, and your account will be frozen.

Report such offers to us and to the cybercrime helpline 1930."""),
    ("Advisory: verify our official communication channels",
     """Dear Client,

We communicate only from our official domain. Beware of lookalike domains and
of messages asking you to click a link to verify your account urgently. When in
doubt, log in through our app or type our website address yourself.

Our SEBI registration number is displayed on our website."""),
]

EXCHANGE_SENDERS = [
    ("NSE Investor Awareness", "msm@nse.co.in"),
    ("BSE Investor Services", "investorservices@bse.co.in"),
    ("NSE Member Services", "international@nse.co.in"),
]
SEBI_SENDER = ("SEBI Office of Investor Assistance", "investorassistance@sebi.gov.in")
BROKER_SENDERS = [
    ("Zerodha Support", "support@zerodha.com"),
    ("Angel One Security", "support@angelone.in"),
]


def _message(name, addr, subject, body, index, *, dkim="pass") -> EmailMessage:
    domain = addr.split("@")[-1]
    msg = EmailMessage()
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Date"] = format_datetime(BASE_DATE - timedelta(hours=index * 5))
    msg["From"] = f"{name} <{addr}>"
    msg["To"] = "investor@example.com"
    msg["Subject"] = subject
    msg["Return-Path"] = f"<bounce@{domain}>"
    msg["Authentication-Results"] = _auth(domain, dkim=dkim)
    msg["Received"] = (f"from mail.{domain} (mail.{domain} [203.0.113.30]) by mx.google.com "
                       f"with ESMTPS id adv{index}; {format_datetime(BASE_DATE)}")
    msg.set_content(body)
    return msg


def _forward_inline(original: EmailMessage) -> EmailMessage:
    """Inline forward: original DKIM destroyed, so the rules must cope alone."""
    fwd = EmailMessage()
    fwd["Message-ID"] = make_msgid(domain="gmail.com")
    fwd["Date"] = format_datetime(BASE_DATE)
    fwd["From"] = "Investor <shourya@gmail.com>"
    fwd["To"] = "check@phishermanai.local"
    fwd["Subject"] = f"Fwd: {original['Subject']}"
    fwd["Authentication-Results"] = _auth("gmail.com")
    fwd.set_content(
        "Received this - is it genuine?\n\n"
        "---------- Forwarded message ----------\n"
        f"From: {original['From']}\n"
        f"Date: {original['Date']}\n"
        f"Subject: {original['Subject']}\n"
        f"To: {original['To']}\n\n"
        f"{original.get_content()}"
    )
    return fwd


def build() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in OUT_DIR.glob("*.eml"):
        stale.unlink()

    manifest = []
    index = 0

    def emit(group, name, addr, subject, body):
        nonlocal index
        direct = _message(name, addr, subject, body, index)
        filename = f"adv_{group}_{index:03d}.eml"
        (OUT_DIR / filename).write_bytes(direct.as_bytes())
        manifest.append({"file": f"adversarial/{filename}", "set": group,
                         "sender": addr, "subject": subject, "variant": "DIRECT",
                         "forward_type": "DIRECT"})
        index += 1
        return direct

    # 15 exchange awareness: 5 texts x 3 senders
    for subject, body in EXCHANGE_AWARENESS:
        for name, addr in EXCHANGE_SENDERS:
            emit("exchange_awareness", name, addr, subject, body)

    # 10 SEBI education: 5 texts, direct + forwarded
    for subject, body in SEBI_EDUCATION:
        direct = emit("sebi_education", SEBI_SENDER[0], SEBI_SENDER[1], subject, body)
        fwd = _forward_inline(direct)
        filename = f"adv_sebi_education_fwd_{index:03d}.eml"
        (OUT_DIR / filename).write_bytes(fwd.as_bytes())
        manifest.append({"file": f"adversarial/{filename}", "set": "sebi_education",
                         "sender": SEBI_SENDER[1], "subject": subject,
                         "variant": "FORWARDED", "forward_type": "INLINE"})
        index += 1

    # 10 broker advisories: 5 texts x 2 senders
    for subject, body in BROKER_ADVISORIES:
        for name, addr in BROKER_SENDERS:
            emit("broker_advisory", name, addr, subject, body)

    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    variants: dict[str, int] = {}
    for item in manifest:
        counts[item["set"]] = counts.get(item["set"], 0) + 1
        variants[item["variant"]] = variants.get(item["variant"], 0) + 1
    return {"total": len(manifest), "by_set": counts, "by_variant": variants,
            "dir": str(OUT_DIR)}


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(build(), indent=2))
