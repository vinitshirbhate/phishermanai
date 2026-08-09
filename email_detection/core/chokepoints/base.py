"""Shared contract for the four chokepoints.

Every securities fraud has to pass through at least one of four places:

    ENTITY    is the claimed sender real and SEBI-registered?
    MONEY     where is the money actually going?
    CLAIM     is what is promised legally possible in India?
    DELIVERY  is the link, app or domain authentic?

Each chokepoint is deterministic, offline and independently testable. None of
them calls a model. They extract nothing and decide nothing about language --
they compare values against reference data loaded from disk.

THREE-VALUED LOGIC
------------------
`passed` is True, False, or None, and None is a first-class answer meaning
"could not determine". A chokepoint that has no evidence must return None, not
False. Returning False on absent evidence is how a system starts calling honest
messages fraud, and that failure mode destroys user trust far faster than a
miss does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# The four chokepoint identifiers.
ENTITY = "ENTITY"
MONEY = "MONEY"
CLAIM = "CLAIM"
DELIVERY = "DELIVERY"


@dataclass
class Reason:
    """One piece of evidence, written for a first-time investor.

    `message` is shown to a real person who may have just lost money, so it is
    plain English naming the concrete thing we found. Not "WHOIS creation_date
    within threshold" but "This link goes to canarabank-dividends.co.in, a
    domain registered 6 days ago."

    `evidence` carries the raw values behind the sentence, so the UI can show
    its working and a reviewer can audit the call.
    """

    code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)
    severity: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    """The outcome of one chokepoint."""

    chokepoint: str
    passed: bool | None                       # None = could not determine
    confidence: float = 0.0                   # 0.0-1.0, how much evidence we had
    severity: int = 0                         # 0-5, how damning a failure is
    reasons: list[Reason] = field(default_factory=list)

    @property
    def max_severity(self) -> int:
        return max((r.severity for r in self.reasons), default=0)

    def add(self, reason: Reason) -> None:
        self.reasons.append(reason)
        self.severity = max(self.severity, reason.severity)

    def sorted_reasons(self) -> list[Reason]:
        return sorted(self.reasons, key=lambda r: -r.severity)

    def consistency_error(self) -> str | None:
        """Is this result internally contradictory? Returns a message or None.

        A check that emitted findings has, by definition, determined something,
        so `passed=None` ("could not determine") alongside real findings is a
        contradiction. It is not a harmless one: the scorer reads passed=None as
        "no evidence" and discounts everything the check said. DELIVERY reported
        exactly this on a phishing email -- four findings, verdict None -- and
        the message came back as NO RISK FOUND.

        Checked by the test suite across every chokepoint rather than raised in
        production: a security tool that crashes on an internal inconsistency
        fails closed, and losing the whole verdict is worse than one bad field.
        """
        if self.passed is None and self.max_severity >= 2:
            codes = [r.code for r in self.sorted_reasons() if r.severity >= 2]
            return (
                f"{self.chokepoint} reports passed=None (could not determine) while "
                f"emitting {len(codes)} finding(s) of severity>=2: {codes}"
            )
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chokepoint": self.chokepoint,
            "passed": self.passed,
            "confidence": round(self.confidence, 3),
            "severity": self.severity,
            "reasons": [r.to_dict() for r in self.sorted_reasons()],
        }

    @classmethod
    def undetermined(cls, chokepoint: str, why: str = "") -> CheckResult:
        """Nothing to check. Explicitly not a failure."""
        result = cls(chokepoint=chokepoint, passed=None, confidence=0.0, severity=0)
        if why:
            result.add(Reason(
                code="NOT_APPLICABLE",
                message=why,
                evidence={},
                severity=0,
            ))
        return result
