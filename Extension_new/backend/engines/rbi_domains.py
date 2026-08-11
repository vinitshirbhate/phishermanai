"""
rbi_domains.py - the `.bank.in` and `.fin.in` exclusive namespaces.

WHY THIS FILE EXISTS
---------------------
A user pointed the extension at `https://www.hdfc.bank.in/` - the genuine
HDFC Bank site - and got DANGER, trust score 14, with these signals:

    [scam] Financial trigger (OTP/KYC/account threat)
    [scam] Lottery/prize scam
    [scam] Domain not in the verified list: bank.in
    [domain] Multiple subdomain levels (2)

Every one of those is wrong, and the last two are wrong in a way that
inverts the signal's meaning.

`.bank.in` is not an ordinary domain. In its February 2025 Statement on
Developmental and Regulatory Policies the RBI created it as an EXCLUSIVE
namespace for Indian banks, with IDRBT (authorised by NIXI under MeitY) as
the sole registrar, and directed every bank to migrate by 31 October 2025.
`.fin.in` is the equivalent for non-bank financial entities. Unlike `.com`
or `.in`, these cannot be bought - only an entity holding a valid RBI
banking licence can obtain one, and registration is centrally verified.

The RBI's own stated purpose for the namespace is anti-phishing: the rule
it gives the public is that if a net-banking address does not end in
`.bank.in`, it is not the bank's official portal.

So `.bank.in` is close to the strongest domain-level trust signal available
in Indian finance, and this codebase was treating it as an unrecognised
TLD with a suspicious subdomain count. The tool was, in effect, warning
users away from the one namespace the regulator built to keep them safe -
and it would have said nothing at all about a `hdfc-bank-secure.com`
lookalike, which is the actual threat.

WHY THE NAIVE PARSER PRODUCED THIS
------------------------------------
Two separate bugs, both from treating `bank.in` as a registrable domain
rather than as an effective TLD (a public suffix):

  1. `www.hdfc.bank.in` splits to [www, hdfc, bank, in]. The depth counter
     in domain_intel.py special-cases `co/gov/org/ac/net` as second-level
     suffixes but not `bank`/`fin`, so it computed depth 2 ("deeply nested
     = suspicious") for what is really one `www` in front of a registrable
     domain.
  2. The whitelist check reduced the host to its last two labels, `bank.in`,
     and reported *that* as unverified - a statement about a public suffix,
     which is meaningless, like saying "`.com` is not on our list".

Note that preflight/psl.js ALREADY lists bank.in correctly. Two domain
parsers in one codebase disagreed, and the wrong one fed the verdict.

CAUTION ABOUT WHAT THIS DOES AND DOES NOT PROVE
-------------------------------------------------
A `.bank.in` domain proves the registrant held an RBI banking licence at
registration time. It does not prove the page is not compromised, that a
subdomain has not been taken over, or that the content is accurate. So
this raises trust and suppresses vocabulary-based scam heuristics; it does
NOT short-circuit blocklist hits, TLS failures, or credential-harvesting
form checks. Those still run and still win.
"""
from __future__ import annotations

import re
from typing import Optional

# Effective TLDs (public suffixes) created by the RBI. A host ending in one
# of these has its registrable domain one label further left than a naive
# last-two-labels split would give.
RBI_SUFFIXES = ("bank.in", "fin.in")

# Other Indian second-level public suffixes, for the same reason. The
# existing depth counter knew some of these; it is centralised here so the
# two domain parsers in this codebase stop disagreeing.
INDIA_SECOND_LEVEL = (
    "co.in", "gov.in", "nic.in", "org.in", "ac.in", "net.in", "edu.in",
    "res.in", "mil.in", "gen.in", "firm.in", "ind.in",
    "bank.in", "fin.in", "insurance.in",
)

TRUST_DELTA_RBI_DOMAIN = +30


def effective_tld(host: str) -> str:
    """Longest known public suffix for this host, else the last label."""
    h = (host or "").lower().strip().rstrip(".")
    for suffix in sorted(INDIA_SECOND_LEVEL, key=len, reverse=True):
        if h == suffix or h.endswith("." + suffix):
            return suffix
    return h.rpartition(".")[2] if "." in h else h


def registrable_domain(host: str) -> str:
    """
    Registrable domain, public-suffix aware.

    `www.hdfc.bank.in` -> `hdfc.bank.in`   (NOT `bank.in`)
    `www.example.co.in` -> `example.co.in`
    `foo.example.com`   -> `example.com`
    """
    h = (host or "").lower().strip().rstrip(".")
    if not h:
        return ""
    etld = effective_tld(h)
    if h == etld:
        return h
    remainder = h[: -(len(etld) + 1)]
    label = remainder.rpartition(".")[2] if "." in remainder else remainder
    return f"{label}.{etld}" if label else h


def subdomain_depth(host: str) -> int:
    """
    Labels in front of the registrable domain.

    `hdfc.bank.in`      -> 0
    `www.hdfc.bank.in`  -> 1   (was 2 under the old counter)
    `a.b.example.com`   -> 2
    """
    h = (host or "").lower().strip().rstrip(".")
    reg = registrable_domain(h)
    if not reg or h == reg:
        return 0
    prefix = h[: -(len(reg) + 1)]
    return len([p for p in prefix.split(".") if p])


def is_rbi_domain(host: str) -> bool:
    """True for a host inside the RBI's licence-gated namespaces."""
    h = (host or "").lower().strip().rstrip(".")
    return any(h == s or h.endswith("." + s) for s in RBI_SUFFIXES)


def classify(host: str) -> Optional[dict]:
    """
    Trust assessment for an RBI-namespace host, or None if not one.

    The wording is written to be shown to a user verbatim, and deliberately
    states the bound of the claim: registration is verified, the page is
    not thereby guaranteed.
    """
    if not is_rbi_domain(host):
        return None
    h = (host or "").lower().strip().rstrip(".")
    kind = "bank" if h.endswith("bank.in") else "financial institution"
    return {
        "rbi_namespace": True,
        "suffix": "bank.in" if h.endswith("bank.in") else "fin.in",
        "registrable_domain": registrable_domain(h),
        "trust_delta": TRUST_DELTA_RBI_DOMAIN,
        "suppress_lexicon": True,
        "signal": (
            f"Registered in the RBI's exclusive .{ 'bank.in' if kind == 'bank' else 'fin.in' } "
            f"namespace, which only a licensed Indian {kind} can obtain "
            "(registrar: IDRBT, under RBI direction)."
        ),
        "caveat": (
            "This confirms who registered the address. It does not by itself "
            "confirm that this particular page is safe — blocklist, "
            "encryption and form checks still apply."
        ),
        "source_url": "https://www.rbi.org.in/",
    }
