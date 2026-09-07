"""Caller-ID verification tier — data/bank_directory.json (directory v2.0.0).

Deterministic caller-identity evidence for the scam-detection pipeline:
  * detect organization claims in the conversation ("Main HBL se bol raha
    hun", "calling from Easypaisa", "FBR ki taraf se") — a claim only counts
    when the mention sits next to a calling-from phrase, so plain mentions
    ("Easypaisa se koi message nahi aya") never fire;
  * verify the caller's number against each claimed organization's
    official_numbers (both normalized) — match => platform_official_channel
    counter-signal (Family D), mismatch => Family-A impersonation evidence
    carrying the organization's directory warning;
  * check the caller ID against the directory's suspicious_patterns
    (mobile spoof, shortcode-as-voice, masked IDs, international routes,
    fake digit runs, ...).

Fictional demo banks (ApnaBank, Metro Commercial Bank) NEVER produce
impersonation evidence or verification verdicts — demo/training traffic
stays isolated from real-world verification (Build Bible Section 17).

Numbers are normalized per the directory's metadata: strip separators, map
letters to telephone-keypad digits, fold +92/0092/92/0 trunk prefixes into a
canonical E.164-ish form; comparison additionally tolerates a shared trailing
9 digits so 111-111-425 and 051-111-111-425 verify as the same UAN.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .engine import ScoringCounterSignal, ScoringSignal
from .rules_engine import normalize as _text_normalize

DEFAULT_DIRECTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "bank_directory.json"

# Max gap (chars) between an organization mention and a calling-from phrase.
CLAIM_PROXIMITY_CHARS = 40

# Directory category -> Family-A impersonation label (services/scoring/taxonomy.py).
CATEGORY_TO_LABEL = {
    "bank": "bank_impersonation",
    "wallet": "wallet_impersonation",
    "telco": "telecom_impersonation",
    "government": "government_impersonation",
    "utility": "utility_impersonation",
    "courier": "courier_impersonation",
    "tech": "tech_support_impersonation",
}

FALLBACK_LABEL = "authority_claim"                 # unknown category -> generic claim
WEAK_NO_CLAIM_LABEL = "unsolicited_contact_origin"  # suspicious number, no org claim

OFFICIAL_CHANNEL_COUNTER = "platform_official_channel"
OFFICIAL_CHANNEL_CONFIDENCE = 0.95
IMPERSONATION_SEVERITY = 5
IMPERSONATION_CONFIDENCE = 0.9
WEAK_CONFIDENCE = 0.5
WEAK_SEVERITY_CAP = 3

# Telephone keypad letter->digit map (ABC=2, DEF=3, ... WXYZ=9).
_KEYPAD: dict[str, str] = {}
for _digit, _chars in enumerate(("ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"), start=2):
    for _ch in _chars:
        _KEYPAD[_ch] = str(_digit)

# Calling-from claim phrases (Roman Urdu + English). An organization mention
# only becomes a *claim* when one of these appears nearby.
_CLAIM_PHRASES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"se bol rah[aei]",        # "HBL se bol raha hun"
        r"se call",                # "NADRA se call kar raha hun"
        r"se phone",               # "Easypaisa se phone aya"
        r"ki taraf se",            # "FBR ki taraf se"
        r"calling (?:you )?from",  # "calling from HBL"
        r"call(?:ing)? from",
        r"speaking (?:to you )?from",
        r"on behalf of",
        r"\brepresent(?:s|ing|ed)?\b",
        r"\bthis is\b.{0,40}\bfrom\b",  # "this is Ali from Meezan Bank"
    )
)

# suspicious_patterns whose applies_to is confined to these scopes never run
# against a bare caller number (they target the message text / SMS sender ID /
# operator attribution only).
_NON_NUMBER_SCOPES = {"caller_id_attribution", "message_text", "sms_sender_id"}


# ================================================================== directory
@lru_cache(maxsize=1)
def _directory() -> dict:
    """Load bank_directory.json exactly once per process."""
    path = os.getenv("BANK_DIRECTORY_PATH") or str(DEFAULT_DIRECTORY_PATH)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _org_matchers() -> tuple[tuple[dict, bool, tuple[re.Pattern[str], ...], tuple[str, ...]], ...]:
    """(org entry, fictional?, whole-word name patterns, normalized official numbers)."""
    directory = _directory()
    entries: list[tuple[dict, bool, tuple[re.Pattern[str], ...], tuple[str, ...]]] = []
    sections = (
        (False, directory.get("organizations", [])),
        (True, (directory.get("fictional_banks") or {}).get("banks", [])),
    )
    for fictional, orgs in sections:
        for org in orgs:
            variants = {str(org.get("name", "")).strip(), str(org.get("short_name", "")).strip()}
            for alias in org.get("aliases", []) or []:
                variants.add(str(alias).strip())
            variants = sorted({v for v in variants if len(v) >= 2}, key=len, reverse=True)
            patterns = tuple(
                re.compile(rf"(?<!\w){re.escape(v)}(?!\w)", re.IGNORECASE) for v in variants
            )
            officials = tuple(
                normalize_number(str(n)) for n in org.get("official_numbers", []) or []
            )
            entries.append((org, fictional, patterns, officials))
    return tuple(entries)


@lru_cache(maxsize=1)
def _number_patterns() -> tuple[tuple[dict, re.Pattern[str]], ...]:
    """suspicious_patterns applicable to a bare caller number, precompiled."""
    out: list[tuple[dict, re.Pattern[str]]] = []
    for spec in _directory().get("suspicious_patterns", []):
        if set(spec.get("applies_to") or []) <= _NON_NUMBER_SCOPES:
            continue
        flags = re.IGNORECASE if "i" in (spec.get("flags") or "") else 0
        out.append((spec, re.compile(spec["pattern"], flags)))
    return tuple(out)


# ================================================================== dataclasses
@dataclass(frozen=True)
class OrgClaim:
    """One organization mention found in the text."""

    name: str
    short_name: str
    category: str
    matched_text: str
    start: int
    end: int
    fictional: bool = False
    warning: str = ""
    official_numbers: tuple[str, ...] = ()  # normalized


@dataclass
class CallerIdResult:
    """Outcome of verifying a set of org claims against the caller's number."""

    caller_number: str = ""
    normalized_caller: str = ""
    claims: list[OrgClaim] = field(default_factory=list)        # real (non-fictional) claims
    verified: list[OrgClaim] = field(default_factory=list)      # number matches official_numbers
    mismatched: list[OrgClaim] = field(default_factory=list)    # claim without official number
    unverifiable: list[OrgClaim] = field(default_factory=list)  # no caller number to check

    @property
    def is_verified(self) -> bool:
        return bool(self.verified)


# ================================================================== numbers
def normalize_number(n: Optional[str]) -> str:
    """Canonical E.164-ish form.

    Keypad letters -> digits ("+92-21-111-APNA-00" -> "+9221111276200"), strip
    spaces/dashes/parens/dots, fold +92 / 0092 / 92 / trunk-0 prefixes:
    "03001234567" and "0092-300-1234567" both become "+923001234567".
    Shortcodes and bare UANs ("3737", "111-111-425") keep their national form.
    """
    if not n:
        return ""
    s = str(n).strip().upper()
    if not s:
        return ""
    digits = "".join(_KEYPAD.get(ch, ch) for ch in s if ch.isdigit() or ch in _KEYPAD)
    if not digits:
        return ""
    has_plus = s.startswith("+")
    if digits.startswith("00"):           # 00 international prefix
        digits = digits[2:]
        has_plus = True
    if has_plus:
        return "+" + digits
    if digits.startswith("92") and len(digits) >= 12:
        return "+" + digits               # country code without '+'
    if digits.startswith("0") and len(digits) >= 10:
        return "+92" + digits[1:]         # trunk prefix '0'
    return digits


def _numbers_match(a: str, b: str) -> bool:
    """Exact normalized equality, or a shared trailing 9 digits (>=9 long)."""
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 9 and len(b) >= 9 and a[-9:] == b[-9:]


# ================================================================== claims
def find_org_mentions(text: str) -> list[OrgClaim]:
    """Every organization mention (whole-word, case-insensitive), real + fictional."""
    cleaned = _text_normalize(text or "")
    if not cleaned:
        return []
    mentions: list[OrgClaim] = []
    for org, fictional, patterns, officials in _org_matchers():
        best: Optional[re.Match] = None
        for pat in patterns:
            for m in pat.finditer(cleaned):
                if best is None or (m.end() - m.start()) > (best.end() - best.start()):
                    best = m
        if best is not None:
            mentions.append(
                OrgClaim(
                    name=str(org.get("name", "")),
                    short_name=str(org.get("short_name", "")),
                    category=str(org.get("category", "")),
                    matched_text=best.group(0),
                    start=best.start(),
                    end=best.end(),
                    fictional=fictional,
                    warning=str(org.get("warning", "")),
                    official_numbers=officials,
                )
            )
    return mentions


def extract_org_claims(text: str) -> list[OrgClaim]:
    """Organizations the speaker claims to represent.

    A mention only counts as a claim when a calling-from phrase ("se bol
    raha", "se call", "ki taraf se", "calling from", ...) appears within
    CLAIM_PROXIMITY_CHARS of it, so plain mentions like "Easypaisa se koi
    message nahi aya" are ignored.
    """
    cleaned = _text_normalize(text or "")
    if not cleaned:
        return []
    claim_spans = [
        (m.start(), m.end()) for pat in _CLAIM_PHRASES for m in pat.finditer(cleaned)
    ]
    if not claim_spans:
        return []
    claims: list[OrgClaim] = []
    for mention in find_org_mentions(text):
        for cs, ce in claim_spans:
            near = cs < mention.end + CLAIM_PROXIMITY_CHARS and ce > mention.start - CLAIM_PROXIMITY_CHARS
            if near:
                claims.append(mention)
                break
    return claims


# ================================================================== verification
def verify_caller(
    claimed_orgs: list[OrgClaim], caller_number: Optional[str]
) -> CallerIdResult:
    """Check each claimed org's official_numbers against the caller's number.

    Fictional (demo) orgs are skipped entirely — they never receive real-world
    verification verdicts.
    """
    raw = str(caller_number).strip() if caller_number else ""
    norm = normalize_number(raw)
    result = CallerIdResult(caller_number=raw, normalized_caller=norm)
    for claim in claimed_orgs:
        if claim.fictional:
            continue
        result.claims.append(claim)
        if not norm:
            result.unverifiable.append(claim)
        elif any(_numbers_match(norm, official) for official in claim.official_numbers):
            result.verified.append(claim)
        else:
            result.mismatched.append(claim)
    return result


def check_suspicious_number(caller_number: Optional[str]) -> list[dict]:
    """Pattern matches from the directory's suspicious_patterns section.

    Each pattern is tested against both the raw and the normalized caller ID;
    patterns scoped to message text / SMS sender IDs / operator attribution
    only are never applied to a bare number.
    """
    if not caller_number:
        return []
    raw = str(caller_number).strip()
    if not raw:
        return []
    norm = normalize_number(raw)
    hits: list[dict] = []
    for spec, pat in _number_patterns():
        matched = False
        for target in (raw, norm):
            if not target:
                continue
            if pat.search(target) if spec.get("match") == "search" else pat.fullmatch(target):
                matched = True
                break
        if matched:
            hits.append(
                {
                    "id": spec.get("id"),
                    "description": spec.get("description", ""),
                    "severity": int(spec.get("severity", 3)),
                    "taxonomy_label": spec.get("taxonomy_label"),
                    "applies_to": list(spec.get("applies_to") or []),
                    "matched": raw,
                }
            )
    return hits


# ================================================================== fusion
def analyze_caller(
    text: str, caller_number: Optional[str]
) -> tuple[list[ScoringSignal], list[ScoringCounterSignal], list[str]]:
    """Full caller-ID analysis of one conversation text against one caller number.

    Returns (signals, counters, warnings) for the deterministic scorer:
      * org claim + number NOT official  -> Family-A impersonation signal
        (severity 5, confidence 0.9, tier 1) + the org's directory warning;
      * org claim + number official      -> platform_official_channel counter
        (confidence 0.95) and nothing else;
      * suspicious caller-ID patterns    -> additional signals mapped to the
        claimed category's label (weak unsolicited_contact_origin when no org
        is claimed);
      * no caller number available       -> nothing (can't verify, don't punish);
      * fictional-only claims            -> nothing (demo traffic, Build Bible 17).
    """
    signals: list[ScoringSignal] = []
    counters: list[ScoringCounterSignal] = []
    warnings: list[str] = []

    raw_number = str(caller_number).strip() if caller_number else ""
    if not raw_number:
        return signals, counters, warnings  # can't verify, don't punish

    claims = extract_org_claims(text or "")
    real_claims = [c for c in claims if not c.fictional]

    # Demo traffic: only fictional banks claimed -> no real-world verdicts at all.
    if claims and not real_claims:
        return signals, counters, warnings

    result = verify_caller(real_claims, raw_number)

    # Verified official channel -> counter-signal only; raw-format suspicion
    # (e.g. shortcode/UAN shape) is overridden by the exact directory match.
    if result.verified:
        counters.append(
            ScoringCounterSignal(type=OFFICIAL_CHANNEL_COUNTER, confidence=OFFICIAL_CHANNEL_CONFIDENCE)
        )
        return signals, counters, warnings

    for claim in result.mismatched:
        label = CATEGORY_TO_LABEL.get(claim.category, FALLBACK_LABEL)
        signals.append(
            ScoringSignal(
                type=label,
                severity=IMPERSONATION_SEVERITY,
                confidence=IMPERSONATION_CONFIDENCE,
                tier=1,
            )
        )
        if claim.warning:
            warnings.append(f"{claim.name}: {claim.warning}")

    pattern_hits = check_suspicious_number(raw_number)
    if result.mismatched:
        # Escalate number patterns that apply to a claimed category; map them
        # onto the claimed org's impersonation label (extra corroborating
        # instance for the scorer's repeat rule).
        claimed_categories = {c.category for c in result.mismatched}
        primary_label = CATEGORY_TO_LABEL.get(result.mismatched[0].category, FALLBACK_LABEL)
        for hit in pattern_hits:
            applies = set(hit.get("applies_to") or [])
            if "any_claim" not in applies and not (applies & claimed_categories):
                continue
            label = hit.get("taxonomy_label") or primary_label
            signals.append(
                ScoringSignal(
                    type=label,
                    severity=int(hit["severity"]),
                    confidence=IMPERSONATION_CONFIDENCE,
                    tier=1,
                )
            )
    else:
        # No organization claimed -> suspicious caller ID alone is a weak signal.
        for hit in pattern_hits:
            label = hit.get("taxonomy_label") or WEAK_NO_CLAIM_LABEL
            signals.append(
                ScoringSignal(
                    type=label,
                    severity=min(int(hit["severity"]), WEAK_SEVERITY_CAP),
                    confidence=WEAK_CONFIDENCE,
                    tier=1,
                )
            )

    return signals, counters, warnings
