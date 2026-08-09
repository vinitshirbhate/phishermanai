"""Build the GENUINE_INSTITUTIONAL fixture class.

    python -m eval.make_institutional

Twenty real-shaped emails from depositories, RTAs, brokers and AMCs: e-voting
notices, re-KYC reminders, CAS statements, IEPF notices, nomination reminders,
contract notes.

WHY THIS CLASS EXISTS
---------------------
This is the false-positive test that matters most, because it is the mail every
demat account holder actually receives. It is deliberately dense with the exact
vocabulary a naive rule set treats as hostile:

    "click here"        every login instruction and unsubscribe footer
    "login / password"  all e-voting instructions
    "OTP"               the depository authenticating you
    "verify your account"  genuine KYC reminders
    "urgent / last date"   real e-voting deadlines
    "PAN"               CDSL legitimately asks for BOID + PAN
    "register"          "Register for Easi"
    "unclaimed dividend"   real IEPF notices
    "account frozen"    genuine re-KYC consequence warnings

Any rule that fires on this class is direction-blind and must be fixed. The
target false-positive rate is zero: a judge with a demat account will paste one
of these in.

The wording follows the structure of genuine notices from CDSL, NSDL, KFin
Technologies, MUFG Intime and CAMS. No real personal data appears -- folio
numbers, DP IDs and amounts are placeholders.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "institutional"

BASE_DATE = datetime(2026, 8, 3, 10, 30)


def _auth(domain: str) -> str:
    return (
        f"mx.google.com; dkim=pass header.i=@{domain} header.s=s1; "
        f"spf=pass smtp.mailfrom=noreply@{domain}; "
        f"dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from={domain}"
    )


# (filename, sender name, sender address, subject, body)
EMAILS: list[tuple[str, str, str, str, str]] = [
    (
        "inst_01_cdsl_evoting.eml",
        "CDSL e-Voting", "helpdesk.evoting@cdslindia.com",
        "Remote e-Voting instructions for shareholders holding shares in demat mode",
        """Dear Demat Account Holder,

As per SEBI circular no. SEBI/HO/CFD/CMD/CIR/P/2020/242 dated December 9, 2020, listed
entities are required to provide remote e-Voting facility to their shareholders.

Individual Shareholders holding securities in Demat mode with CDSL:

1. Users who have opted for CDSL Easi / Easiest facility can login through their existing
   user id and password. Click here to login: https://web.cdslindia.com/myeasi/home/login
2. If the user is not registered for Easi/Easiest, the option to register is available at
   https://web.cdslindia.com/myeasi/Registration/EasiRegistration
3. Alternatively, the user can directly access the e-Voting page by providing Demat
   Account Number and PAN from the e-Voting link available on www.cdslindia.com home page.
   The system will authenticate the user by sending OTP on registered Mobile & Email as
   recorded in the Demat Account.

The last date to cast your vote is 11 August 2026 at 5:00 P.M.

For any technical assistance please contact our toll free no. 1800 22 55 33.

Central Depository Services (India) Limited""",
    ),
    (
        "inst_02_nsdl_evoting.eml",
        "NSDL e-Voting", "evoting@nsdl.com",
        "Login instructions for NSDL e-Voting system - AGM 2026",
        """Dear Shareholder,

Individual Shareholders holding securities in demat mode with NSDL may follow the steps
below to cast their vote:

1. Visit the e-Services website of NSDL at https://eservices.nsdl.com and click on
   "Beneficial Owner" under "IDeAS" section.
2. Enter your existing User ID and Password. After successful authentication you will be
   able to see the e-Voting services.
3. If you have not registered for IDeAS, please register at https://eservices.nsdl.com

A One Time Password will be sent to your registered mobile number for verification.
Please do not share your password with anyone. NSDL will never ask you for your password.

Your User ID is your 8 character DP ID followed by 8 digit Client ID.

In case of any grievances connected with the e-Voting facility, please write to
evoting@nsdl.com or call our toll free number 1800 1020 990.

National Securities Depository Limited""",
    ),
    (
        "inst_03_kfin_agm.eml",
        "KFin Technologies", "einward.ris@kfintech.com",
        "Notice of 42nd Annual General Meeting and e-Voting information",
        """Dear Member,

Notice is hereby given that the 42nd Annual General Meeting will be held on Tuesday,
25 August 2026 at 11:00 A.M. through Video Conferencing.

The remote e-Voting period commences on Saturday, 22 August 2026 at 9:00 A.M. and ends
on Monday, 24 August 2026 at 5:00 P.M. The cut-off date for determining eligibility is
Monday, 18 August 2026.

Members holding shares in physical form who have not registered their email address may
register by clicking here: https://ris.kfintech.com/email_registration

Members are requested to update their PAN, bank mandate and nomination details with their
Depository Participant. As per SEBI circular, folios without PAN and nomination are liable
to be frozen for payment of dividend.

KFin Technologies Limited
Registrar and Share Transfer Agent""",
    ),
    (
        "inst_04_mufg_dividend.eml",
        "MUFG Intime India", "investor.helpdesk@linkintime.co.in",
        "Intimation of record date for payment of final dividend",
        """Dear Shareholder,

This is to inform you that the Record Date for the purpose of determining the members
eligible to receive the final dividend has been fixed as Friday, 21 August 2026.

The dividend will be credited directly to the bank account registered with your
Depository Participant. No action or payment is required from you.

Members who have not updated their bank mandate are requested to do so at the earliest
through their Depository Participant, failing which the dividend will be kept in
abeyance and transferred to the Unpaid Dividend Account.

For queries please write to investor.helpdesk@linkintime.co.in

MUFG Intime India Private Limited""",
    ),
    (
        "inst_05_iepf_unclaimed.eml",
        "KFin Technologies", "iepf.ris@kfintech.com",
        "Unclaimed dividend liable to be transferred to IEPF - action required",
        """Dear Shareholder,

Pursuant to Sections 124 and 125 of the Companies Act, 2013, dividends which remain
unclaimed for a period of seven consecutive years are required to be transferred to the
Investor Education and Protection Fund (IEPF) established by the Central Government.

Our records indicate that dividend declared for the financial year 2018-19 remains
unclaimed against your folio. If the unclaimed dividend is not claimed on or before
30 September 2026, the shares will also be transferred to the IEPF Authority.

To claim the unclaimed dividend, please submit Form IEPF-5 through the MCA portal and
send the physical documents to the Registrar and Transfer Agent at the address below.

No fee is payable to the Company or the Registrar for this claim.

KFin Technologies Limited
Registrar and Share Transfer Agent""",
    ),
    (
        "inst_06_rekyc_reminder.eml",
        "Zerodha Support", "support@zerodha.com",
        "Re-KYC required for your trading and demat account",
        """Hello,

As per SEBI regulations, your KYC details need to be periodically updated. Our records
show that your KYC is due for revalidation.

Please complete your re-KYC at your convenience by logging in to Console at
https://console.zerodha.com/profile/kyc

If the re-KYC is not completed, your trading account may be restricted for new
positions until the update is done. Your existing holdings remain safe and are held
with the depository.

We will never ask you for your password, OTP or PIN over a call or message. If anyone
asks you to share these, please report it to us immediately.

Zerodha Broking Limited
SEBI Registration: INZ000031633""",
    ),
    (
        "inst_07_cams_cas.eml",
        "CAMS", "camsCAS@camsonline.com",
        "Consolidated Account Statement for July 2026",
        """Dear Investor,

Please find attached your Consolidated Account Statement (CAS) for the month of
July 2026, covering your mutual fund and demat holdings.

The statement is password protected. Your password is your PAN in upper case.

To view your holdings online, please login at https://www.camsonline.com with your
registered email address. An OTP will be sent to your registered mobile number for
authentication.

Mutual fund investments are subject to market risks. Read all scheme related documents
carefully before investing.

Computer Age Management Services Limited""",
    ),
    (
        "inst_08_nomination_reminder.eml",
        "MUFG Intime India", "rnt.helpdesk@linkintime.co.in",
        "Nomination update required for your folio",
        """Dear Shareholder,

As per SEBI circular, all holders of physical securities are required to furnish
nomination details or submit a declaration to opt out of nomination.

Folios which do not comply are liable to be frozen for payment of dividend, interest or
redemption, and for lodging any service request.

Please submit Form SH-13 (nomination) or Form ISR-3 (opt out) to the Registrar. Forms are
available at https://in.mpms.mufg.com/Downloads.html

There is no charge for updating nomination details.

MUFG Intime India Private Limited""",
    ),
    (
        "inst_09_broker_contract_note.eml",
        "Angel One", "contractnotes@angelone.in",
        "Contract note for trades dated 03 August 2026",
        """Dear Client,

Please find attached the digitally signed contract note for trades executed on
03 August 2026.

The attachment is password protected. The password is your PAN in upper case.

You can also view your trades and download reports by logging in to
https://www.angelone.in with your Client ID and password.

Please verify the details and report any discrepancy within 24 hours to
support@angelone.in or call our helpline 1800 1020 330.

Angel One Limited
SEBI Registration: INZ000161534""",
    ),
    (
        "inst_10_postal_ballot.eml",
        "Company Secretary", "investor.relations@ril.com",
        "Postal ballot notice and remote e-voting instructions",
        """Dear Member,

Notice of Postal Ballot dated 17 July 2026 is being sent to all members whose email
addresses are registered with the Company or the Depository.

Remote e-voting commences on Friday, 24 July 2026 at 9:00 A.M. and ends on Saturday,
23 August 2026 at 5:00 P.M. E-voting shall not be allowed beyond the said date and time.

Members holding shares in demat mode may cast their vote through the NSDL e-voting system
using their existing login credentials. Members who have forgotten their password may use
the "Forgot User Details/Password" option available on the portal.

The Company has appointed a Scrutinizer for conducting the postal ballot process in a
fair and transparent manner.

Reliance Industries Limited""",
    ),
    (
        "inst_11_rights_issue.eml",
        "KFin Technologies", "rightsissue.ris@kfintech.com",
        "Rights issue - application form and ASBA instructions",
        """Dear Shareholder,

The Company has announced a Rights Issue. The Rights Entitlement has been credited to your
demat account.

You may apply through the ASBA facility by submitting the application to your Self
Certified Syndicate Bank, or online at https://rights.kfintech.com

Please note that the issue closes on 28 August 2026. Applications received after the
closing date will not be considered.

Do not make any payment to any individual. Application money is blocked in your own bank
account under ASBA and is debited only on allotment.

KFin Technologies Limited""",
    ),
    (
        "inst_12_sebi_investor_charter.eml",
        "Kotak Securities", "service.securities@kotak.com",
        "Investor Charter and grievance redressal mechanism",
        """Dear Client,

In accordance with SEBI circular, we are sharing the Investor Charter setting out the
services provided to investors and their rights.

If you have a grievance, please write to service.securities@kotak.com. If your complaint
is not resolved within 30 days, you may lodge a complaint on the SEBI SCORES portal at
https://scores.sebi.gov.in or through the SMART ODR portal at https://smartodr.in

Beware of fraudsters. Do not share your login credentials, OTP or PIN with anyone,
including persons claiming to be from our support team.

Kotak Securities Limited""",
    ),
    (
        "inst_13_buyback.eml",
        "Company Secretary", "secretarial@infosys.com",
        "Buyback of equity shares - letter of offer",
        """Dear Shareholder,

The Board has approved a buyback of fully paid-up equity shares. The Letter of Offer and
Tender Form are being dispatched to all eligible shareholders as on the record date.

Shareholders holding shares in demat form must submit their tender through their broker
during the tendering period, which opens on 18 August 2026 and closes on 25 August 2026.

Please note that no payment is required to participate. Shares accepted in the buyback
will be paid for directly to your registered bank account.

Infosys Limited""",
    ),
    (
        "inst_14_dp_charges.eml",
        "HDFC Securities", "customercare@hdfcsec.com",
        "Annual maintenance charges for your demat account",
        """Dear Customer,

The annual maintenance charge for your demat account for FY 2026-27 will be debited from
your linked trading account on 15 August 2026 as per the tariff you accepted at account
opening.

Please ensure sufficient balance in your trading account. If the AMC remains unpaid, the
demat account may be suspended for debit as per depository rules.

You can view the tariff sheet after logging in at https://www.hdfcsec.com

HDFC Securities Limited""",
    ),
    (
        "inst_15_mf_nfo.eml",
        "SBI Mutual Fund", "customer.delight@sbimf.com",
        "New Fund Offer - scheme information document",
        """Dear Investor,

The New Fund Offer opens on 10 August 2026 and closes on 24 August 2026.

You may invest through your distributor, through https://www.sbimf.com, or through the
MF Central portal at https://www.mfcentral.com

Minimum application amount is Rs 5,000. Units will be allotted at Rs 10 per unit during
the NFO period.

Mutual fund investments are subject to market risks. Read all scheme related documents
carefully before investing. Past performance is not indicative of future results. There
is no assurance or guarantee of returns.

SBI Funds Management Limited""",
    ),
    (
        "inst_16_account_frozen_kyc.eml",
        "MUFG Intime India", "isr.helpdesk@linkintime.co.in",
        "Folio frozen - KYC documents pending",
        """Dear Shareholder,

As per SEBI circular, folios in which any of PAN, KYC details, nomination or bank mandate
are not available are liable to be frozen.

Our records show your folio has been frozen for want of the above documents.

To unfreeze the folio, please submit Form ISR-1 along with self-attested copies of PAN and
address proof to the Registrar and Transfer Agent. There is no fee for this service.

You may download the forms from https://in.mpms.mufg.com/Downloads.html

MUFG Intime India Private Limited""",
    ),
    (
        "inst_17_upi_mandate.eml",
        "Groww", "support@groww.in",
        "SIP mandate registration confirmation",
        """Hi,

Your SIP mandate has been registered successfully. The first instalment will be debited
on 10 August 2026.

Please approve the UPI mandate request in your UPI application. The collect request will
appear from our validated intermediary handle groww.mf@valid.

You can view or cancel the mandate anytime from the Groww app under SIPs.

Mutual fund investments are subject to market risks. Read all scheme related documents
carefully.

Groww Invest Tech Private Limited""",
    ),
    (
        "inst_18_password_reset.eml",
        "Upstox", "no-reply@upstox.com",
        "Password reset request for your account",
        """Hello,

We received a request to reset the password for your Upstox account.

Click here to reset your password: https://www.upstox.com/account/reset-password

This link will expire in 30 minutes. If you did not request a password reset, please
ignore this email and your password will remain unchanged.

For security, we will never ask you to share your password, OTP or PIN. If someone
contacts you asking for these, do not share them and report it to us.

Upstox Securities Private Limited""",
    ),
    (
        "inst_19_bse_corporate_action.eml",
        "Company Secretary", "investors@titancompany.in",
        "Intimation of book closure for AGM and dividend",
        """Dear Shareholder,

Pursuant to Regulation 42 of the SEBI (Listing Obligations and Disclosure Requirements)
Regulations, 2015, notice is hereby given that the Register of Members will remain closed
from Monday, 17 August 2026 to Friday, 21 August 2026 (both days inclusive) for the
purpose of the Annual General Meeting and payment of dividend.

The dividend, if declared, will be paid on or after 1 September 2026 to those members
whose names appear on the register as on the book closure date.

This communication is for information only. No action or payment is required from you.

Titan Company Limited""",
    ),
    (
        "inst_20_demat_statement.eml",
        "NSDL", "statements@nsdl.com",
        "Transaction statement for your demat account - July 2026",
        """Dear Client,

The transaction statement for your demat account for the period 1 July 2026 to
31 July 2026 is attached.

To view your holdings online, register for the IDeAS facility at
https://eservices.nsdl.com. After registration you can login with your user ID and
password to view holdings across your demat accounts.

Please verify the transactions in the statement. If you notice any discrepancy, contact
your Depository Participant immediately.

NSDL will never call or email you asking for your password, OTP or IDeAS credentials.

National Securities Depository Limited""",
    ),
]


def build() -> dict:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for index, (filename, sender_name, sender_addr, subject, body) in enumerate(EMAILS):
        domain = sender_addr.split("@")[-1]
        msg = EmailMessage()
        msg["Message-ID"] = make_msgid(domain=domain)
        msg["Date"] = format_datetime(BASE_DATE - timedelta(hours=index * 7))
        msg["From"] = f"{sender_name} <{sender_addr}>"
        msg["To"] = "investor@example.com"
        msg["Subject"] = subject
        msg["Return-Path"] = f"<bounce@{domain}>"
        msg["Authentication-Results"] = _auth(domain)
        msg["Received"] = (
            f"from mail.{domain} (mail.{domain} [203.0.113.20]) by mx.google.com "
            f"with ESMTPS id inst{index}; {format_datetime(BASE_DATE)}"
        )
        msg.set_content(body)

        path = FIXTURE_DIR / filename
        path.write_bytes(msg.as_bytes())
        manifest.append({
            "file": f"institutional/{filename}",
            "label": "GENUINE_INSTITUTIONAL",
            "sender": sender_addr,
            "domain": domain,
            "subject": subject,
        })

    (FIXTURE_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return {"written": len(manifest), "dir": str(FIXTURE_DIR)}


if __name__ == "__main__":  # pragma: no cover
    result = build()
    print(json.dumps(result, indent=2))
