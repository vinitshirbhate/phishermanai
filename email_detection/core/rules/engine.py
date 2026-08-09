"""Contextual rule engine.

A rule may not match a noun. It must declare what ACTION accompanies the noun
and in which DIRECTION the thing is travelling.

    "sending OTP on registered Mobile"     institution -> user   harmless
    "share the OTP with me"                user -> attacker      severity 5

Both contain the token "OTP" next to a verb. Only the direction separates them,
and a flat regex list cannot see it. Every confirmed false positive in this
project has had this shape.

EVALUATION ORDER -- cheapest first, fail fast
---------------------------------------------
    1. entity present?              no  -> no fire
    2. suppressor in window?        yes -> no fire  (logged)
    3. action present in window?    no  -> no fire
    4. direction consistent?        no  -> no fire
    5. requires_ask satisfied?      no  -> no fire
    -> fire

A rule that cannot express an action and a direction is not a rule. It is a
keyword, and keywords are capped at severity 1 -- informational, never
verdict-changing.

Suppressions are logged with the rule id and the matched suppressor, so what
nearly fired is visible rather than silent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger("phishermanai.rules")


class Direction(str, Enum):
    """Which way the thing described by the rule is travelling."""

    FROM_USER = "FROM_USER"        # the user is being asked to give something up
    TO_USER = "TO_USER"            # something is being delivered to the user
    UNSPECIFIED = "UNSPECIFIED"    # direction carries no meaning for this rule


# Phrases showing something flows TO the user. Their presence contradicts a
# FROM_USER rule. Deliberately generous: a missed fraud costs less than a false
# accusation against a real bank.
TO_USER_MARKERS = re.compile(
    r"(?:will\s+be|shall\s+be|is|has\s+been|have\s+been|would\s+be|been)\s+"
    r"(?:sent|delivered|credited|issued|dispatched|provided|shared|mailed|generated)"
    r"\s*(?:to|on|with)?\s*(?:you|your|the\s+registered|registered)"
    r"|you\s+will\s+(?:receive|get)"
    r"|(?:sent|delivered|credited)\s+to\s+your"
    r"|we\s+(?:will\s+)?(?:send|issue|provide|share)\s+you"
    r"|(?:sending|send)\s+(?:an?\s+)?\w{1,12}\s+(?:on|to)\s+(?:your\s+)?registered"
    r"|authenticat\w+\s+(?:the\s+)?(?:user|you)\s+by",
    re.I,
)

# Phrases showing the user is being asked to hand something over.
FROM_USER_MARKERS = re.compile(
    r"\b(?:share|send|provide|give|tell|forward|reveal|disclose|submit|enter|type|"
    r"confirm|transfer|remit|deposit|pay|credit)\b[^.!?\n]{0,24}"
    r"\b(?:me|us|it|the|your|to\s+(?:this|the|below|following))\b"
    r"|\bto\s+(?:my|our|this|the\s+below|the\s+following)\b",
    re.I,
)

# Does the message ask the reader to DO something? A statement that requests
# nothing has no fraud mechanism.
ASK_MARKERS = re.compile(
    r"\b(?:please|kindly|you\s+(?:must|need\s+to|have\s+to|should|are\s+required)|"
    r"click|call|contact|reply|respond|send|share|pay|transfer|deposit|remit|"
    r"submit|provide|confirm|verify|update|register|download|install|join|"
    r"scan|enter|complete|act\s+now|hurry|apply)\b"
    r"|\?",
    re.I,
)


@dataclass
class Rule:
    """One contextual rule."""

    id: str
    entity: re.Pattern[str]
    action: re.Pattern[str] | None
    direction: Direction
    suppressors: list[re.Pattern[str]] = field(default_factory=list)
    window: int = 120
    requires_ask: bool = True
    severity: int = 3
    rule_type: str = "OTHER"
    explanation: str = ""
    legal_basis: str | None = None

    def __post_init__(self) -> None:
        # A rule with no action cannot establish intent, so it may only ever be
        # informational. Enforced here rather than trusted to the data file.
        if self.action is None and self.severity > 1:
            raise ValueError(
                f"rule {self.id}: no action declared, so severity must be <= 1 "
                f"(got {self.severity}). A rule without an action is a keyword."
            )


@dataclass
class RuleHit:
    rule_id: str
    severity: int
    rule_type: str
    matched_text: str
    start: int
    end: int
    explanation: str
    legal_basis: str | None
    action_matched: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id, "severity": self.severity,
            "matched_text": self.matched_text, "span": [self.start, self.end],
            "rule_type": self.rule_type, "action_matched": self.action_matched,
            "legal_basis": self.legal_basis,
        }


@dataclass
class Suppression:
    rule_id: str
    reason: str                # SUPPRESSOR | NO_ACTION | WRONG_DIRECTION | NO_ASK
    matched_text: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "reason": self.reason,
                "matched_text": self.matched_text[:80], "detail": self.detail[:120]}


@dataclass
class EvaluationResult:
    hits: list[RuleHit] = field(default_factory=list)
    suppressions: list[Suppression] = field(default_factory=list)
    message_is_asking: bool = False

    @property
    def max_severity(self) -> int:
        return max((h.severity for h in self.hits), default=0)


def message_is_asking(text: str) -> bool:
    """Does this message request an action from the reader?

    A message that asks for nothing cannot be executing a fraud: there is no
    mechanism. Statements, receipts and notices fall here.
    """
    return bool(ASK_MARKERS.search(text or ""))


def _window(text: str, start: int, end: int, size: int) -> tuple[str, int]:
    lo = max(0, start - size)
    hi = min(len(text), end + size)
    return text[lo:hi], lo


def evaluate(rules: list[Rule], text: str) -> EvaluationResult:
    """Run every rule over `text` in the documented order."""
    result = EvaluationResult()
    if not text:
        return result

    asking = message_is_asking(text)
    result.message_is_asking = asking

    for rule in rules:
        for match in rule.entity.finditer(text):
            context, _offset = _window(text, match.start(), match.end(), rule.window)

            # 2. suppressors
            suppressed = None
            for suppressor in rule.suppressors:
                found = suppressor.search(context)
                if found:
                    suppressed = found.group(0)
                    break
            if suppressed is not None:
                result.suppressions.append(Suppression(
                    rule_id=rule.id, reason="SUPPRESSOR",
                    matched_text=match.group(0), detail=suppressed,
                ))
                continue

            # 3. action
            action_text = None
            if rule.action is not None:
                action_match = rule.action.search(context)
                if action_match is None:
                    result.suppressions.append(Suppression(
                        rule_id=rule.id, reason="NO_ACTION",
                        matched_text=match.group(0),
                    ))
                    continue
                action_text = action_match.group(0)

            # 4. direction
            if rule.direction is Direction.FROM_USER:
                if TO_USER_MARKERS.search(context) and not FROM_USER_MARKERS.search(context):
                    result.suppressions.append(Suppression(
                        rule_id=rule.id, reason="WRONG_DIRECTION",
                        matched_text=match.group(0),
                        detail="context describes delivery TO the user",
                    ))
                    continue
            elif rule.direction is Direction.TO_USER:
                if FROM_USER_MARKERS.search(context) and not TO_USER_MARKERS.search(context):
                    result.suppressions.append(Suppression(
                        rule_id=rule.id, reason="WRONG_DIRECTION",
                        matched_text=match.group(0),
                    ))
                    continue

            # 5. requires_ask
            if rule.requires_ask and not asking:
                result.suppressions.append(Suppression(
                    rule_id=rule.id, reason="NO_ASK",
                    matched_text=match.group(0),
                    detail="message requests no action from the reader",
                ))
                continue

            result.hits.append(RuleHit(
                rule_id=rule.id, severity=rule.severity, rule_type=rule.rule_type,
                matched_text=match.group(0), start=match.start(), end=match.end(),
                explanation=rule.explanation, legal_basis=rule.legal_basis,
                action_matched=action_text,
            ))
            break   # one hit per rule is enough; the rest is noise

    for suppression in result.suppressions:
        log.debug("suppressed %s (%s): %r [%s]", suppression.rule_id,
                  suppression.reason, suppression.matched_text, suppression.detail)

    return result


def compile_rule(row: dict[str, Any]) -> Rule | None:
    """Build a Rule from a CSV row. Returns None if it cannot be compiled.

    A rule that fails to compile disables itself rather than taking the whole
    engine down, and a rule whose SUPPRESSOR fails to compile is disabled too --
    a half-loaded rule would fire on the legitimate mail its suppressor exists
    to protect.
    """
    rule_id = (row.get("id") or row.get("code") or "").strip()
    entity_pattern = (row.get("entity") or row.get("pattern") or "").strip()
    if not rule_id or not entity_pattern:
        return None

    try:
        entity = re.compile(entity_pattern, re.I | re.U)
    except re.error as exc:
        log.error("rule %s: entity pattern failed to compile (%s)", rule_id, exc)
        return None

    action = None
    action_pattern = (row.get("action") or "").strip()
    if action_pattern:
        try:
            action = re.compile(action_pattern, re.I | re.U)
        except re.error as exc:
            log.error("rule %s: action pattern failed to compile (%s)", rule_id, exc)
            return None

    suppressors: list[re.Pattern[str]] = []
    raw_suppressors = (row.get("suppressors") or "").strip()
    if raw_suppressors:
        for piece in raw_suppressors.split("|||"):
            piece = piece.strip()
            if not piece:
                continue
            try:
                suppressors.append(re.compile(piece, re.I | re.U))
            except re.error as exc:
                log.error("rule %s: suppressor failed to compile (%s) - rule DISABLED", rule_id, exc)
                return None

    try:
        direction = Direction((row.get("direction") or "UNSPECIFIED").strip().upper())
    except ValueError:
        direction = Direction.UNSPECIFIED

    def _flag(name: str, default: bool) -> bool:
        raw = str(row.get(name, "")).strip().lower()
        if raw in ("1", "true", "yes"):
            return True
        if raw in ("0", "false", "no"):
            return False
        return default

    try:
        return Rule(
            id=rule_id,
            entity=entity,
            action=action,
            direction=direction,
            suppressors=suppressors,
            window=int(row.get("window") or 120),
            requires_ask=_flag("requires_ask", True),
            severity=int(row.get("severity") or 3),
            rule_type=(row.get("rule_type") or "OTHER").strip(),
            explanation=(row.get("explanation") or "").strip(),
            legal_basis=(row.get("legal_basis") or "").strip() or None,
        )
    except ValueError as exc:
        log.error("rule %s rejected: %s", rule_id, exc)
        return None
