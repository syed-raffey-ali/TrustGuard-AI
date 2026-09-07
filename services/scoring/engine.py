"""TrustGuard deterministic scoring engine — Build Bible Section 15, EXACTLY.

The LLM never computes the score. This module is the ONLY score producer.

Pipeline (order derived from Section 15.4 + the worked examples of 15.5):
  1. per-signal contribution: base = weight * (severity/5) * confidence;
     repeats of the same label add 8% each, capped at +30% of that base.
  2. counter-signals sum with weight*confidence, total capped at -15.
  3. raw = positives + capped negatives.
  4. source ceiling:
       - no strong Tier-2 AND no trained-tier (ML) signal -> raw capped at 24
       - trained-tier signals present but no strong Tier-2 -> raw capped at 74
         (ML alone can reach High but not Critical, per Bible §3)
  5. modifiers: chronology +10, corroboration +15, cross_channel +10,
     uncertainty -(1 - mean_positive_confidence) * 12.
  6. clamp to 0..100.
  7. context_floor: unknown caller AND any Family-A signal -> floor at 25.
  8. ratchet: displayed score may fall at most 5 points per scoring cycle.

Worked examples in tests/test_scoring.py are unit-test targets (±0.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .taxonomy import (
    FAMILY_A_IMPERSONATION,
    FAMILY_B_FINANCIAL_CREDENTIAL,
    LABELS,
    band_for_score,
)

FREQ_STEP = 0.08          # repeats add 8% each
FREQ_CAP = 0.30           # ...capped at 30% of the signal's base
COUNTER_CAP = -15.0       # total negative floor per cycle
TIER1_ONLY_CAP = 24.0     # Tier-1-only can never exceed Medium ceiling
ML_ONLY_CAP = 74.0        # Trained-tier (tier=15) can reach High but not Critical
TIER2_STRONG_CONFIDENCE = 0.70   # below this (Tier-2 absent/weak) the cap applies
CHRONOLOGY_BONUS = 10.0
CORROBORATION_BONUS = 15.0
CROSS_CHANNEL_BONUS = 10.0
UNCERTAINTY_FACTOR = 12.0
CONTEXT_FLOOR = 25.0      # unknown caller + impersonation floor
CLAMP_MIN, CLAMP_MAX = 0.0, 100.0
RATCHET_MAX_FALL = 5.0    # displayed score falls at most 5 points per cycle
CHRONOLOGY_WINDOW_S = 120.0     # voice channel window
CHRONOLOGY_WINDOW_MSGS = 3      # text channel window


@dataclass
class ScoringSignal:
    """One detected scam signal instance (from rules engine or Tier-2 LLM)."""

    type: str
    severity: int                 # 1..5
    confidence: float             # 0..1
    tier: int = 2                 # 1 (rules) or 2 (LLM)
    position_s: Optional[float] = None    # voice timeline position, seconds
    message_index: Optional[int] = None   # text channel message index


@dataclass
class ScoringCounterSignal:
    type: str
    confidence: float


@dataclass
class ScoringContext:
    unknown_caller: bool = False
    cross_channel_otp: bool = False   # OTP-format chat msg arrived during a call within 60 s


@dataclass
class SignalContribution:
    label: str
    family: str
    weight: float
    severity_norm: float
    confidence: float
    instances: int
    base: float
    frequency_bonus: float
    contribution: float
    tier: int


@dataclass
class ScoringResult:
    score: float
    band: str
    raw: float
    positive_total: float
    negative_total: float
    contributions: list[SignalContribution] = field(default_factory=list)
    chronology_applied: bool = False
    corroboration_applied: bool = False
    cross_channel_applied: bool = False
    uncertainty_penalty: float = 0.0
    tier1_cap_applied: bool = False
    context_floor_applied: bool = False
    ratcheted_from: Optional[float] = None


def _chronology_hit(a: ScoringSignal, b: ScoringSignal) -> bool:
    """Family-B within 120 s of speech OR 3 messages of a Family-A signal."""
    if a.message_index is not None and b.message_index is not None:
        return abs(a.message_index - b.message_index) <= CHRONOLOGY_WINDOW_MSGS
    if a.position_s is not None and b.position_s is not None:
        return abs(a.position_s - b.position_s) <= CHRONOLOGY_WINDOW_S
    return False


def score_conversation(
    signals: Iterable[ScoringSignal],
    counters: Iterable[ScoringCounterSignal] = (),
    context: ScoringContext | None = None,
    previous_displayed_score: Optional[float] = None,
) -> ScoringResult:
    ctx = context or ScoringContext()
    signals = [s for s in signals if s.type in LABELS]
    counters = [c for c in counters if c.type in LABELS]

    contributions: list[SignalContribution] = []
    positive_total = 0.0

    # ---- 1. group by label; strongest instance sets the base, repeats add 8% each (cap +30%)
    by_type: dict[str, list[ScoringSignal]] = {}
    for s in signals:
        by_type.setdefault(s.type, []).append(s)

    for label, instances in by_type.items():
        definition = LABELS[label]
        if definition.weight < 0:
            continue  # Family-D labels only enter via counters
        norm_sev = max(0, min(5, instances[0].severity)) / 5.0
        best = max(instances, key=lambda s: (s.confidence, s.severity))
        base = definition.weight * norm_sev * best.confidence
        n = len(instances)
        freq = min(base * FREQ_STEP * (n - 1), base * FREQ_CAP)
        contribution = base + freq
        positive_total += contribution
        contributions.append(
            SignalContribution(
                label=label,
                family=definition.family,
                weight=definition.weight,
                severity_norm=norm_sev,
                confidence=best.confidence,
                instances=n,
                base=base,
                frequency_bonus=freq,
                contribution=contribution,
                tier=min(i.tier for i in instances),
            )
        )

    # ---- 2. counter-signals, total capped at -15
    negative_total = 0.0
    for c in counters:
        definition = LABELS[c.type]
        if definition.weight >= 0:
            continue
        negative_total += definition.weight * max(0.0, min(1.0, c.confidence))
    negative_total = max(negative_total, COUNTER_CAP)

    raw = positive_total + negative_total

    # ---- 3. Source ceiling (tiered trust hierarchy)
    #   Tier-1 only (regex)                 -> cap 24  (Medium at most)
    #   Trained tier (ML, tier=15) present  -> cap 74  (High at most)
    #   Strong Tier-2 LLM confirmation      -> no cap  (Critical reachable)
    tier2_strong = any(
        s.tier == 2 and s.confidence >= TIER2_STRONG_CONFIDENCE for s in signals
    )
    has_ml = any(s.tier == 15 for s in signals)
    tier1_cap_applied = False
    if not tier2_strong:
        if has_ml:
            if raw > ML_ONLY_CAP:
                raw = ML_ONLY_CAP
                tier1_cap_applied = True
        elif raw > TIER1_ONLY_CAP:
            raw = TIER1_ONLY_CAP
            tier1_cap_applied = True

    # ---- 4. modifiers
    family_a = [s for s in signals if LABELS[s.type].family == FAMILY_A_IMPERSONATION]
    family_b = [s for s in signals if LABELS[s.type].family == FAMILY_B_FINANCIAL_CREDENTIAL]

    chronology = any(_chronology_hit(b, a) for b in family_b for a in family_a)
    corroboration = (
        any(s.confidence >= 0.80 for s in family_a)
        and any(s.confidence >= 0.80 for s in family_b)
    )
    cross_channel = bool(ctx.cross_channel_otp)

    confidences = [s.confidence for s in signals]
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    uncertainty = (1.0 - mean_conf) * UNCERTAINTY_FACTOR if confidences else 0.0

    scored = raw
    scored += CHRONOLOGY_BONUS if chronology else 0.0
    scored += CORROBORATION_BONUS if corroboration else 0.0
    scored += CROSS_CHANNEL_BONUS if cross_channel else 0.0
    scored -= uncertainty

    # ---- 5. clamp
    scored = max(CLAMP_MIN, min(CLAMP_MAX, scored))

    # ---- 6. context floor AFTER clamp so the floor itself survives uncertainty
    context_floor_applied = False
    if ctx.unknown_caller and family_a and scored < CONTEXT_FLOOR:
        scored = CONTEXT_FLOOR
        context_floor_applied = True

    # ---- 7. ratchet — a scammer cannot reset the warning by changing subject
    ratcheted_from = None
    if previous_displayed_score is not None:
        floor_allowed = previous_displayed_score - RATCHET_MAX_FALL
        if scored < floor_allowed:
            ratcheted_from = previous_displayed_score
            scored = floor_allowed

    score_rounded = round(scored, 2)
    return ScoringResult(
        score=score_rounded,
        band=band_for_score(score_rounded),
        raw=round(raw, 2),
        positive_total=round(positive_total, 2),
        negative_total=round(negative_total, 2),
        contributions=sorted(contributions, key=lambda c: -c.contribution),
        chronology_applied=chronology,
        corroboration_applied=corroboration,
        cross_channel_applied=cross_channel,
        uncertainty_penalty=round(uncertainty, 2),
        tier1_cap_applied=tier1_cap_applied,
        context_floor_applied=context_floor_applied,
        ratcheted_from=ratcheted_from,
    )
