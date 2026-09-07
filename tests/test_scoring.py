"""Unit-test targets: Build Bible Section 15.5 worked examples (±0.5),
the ratchet rule, the Tier-1-only cap, and the counter-signal cap.

Run:  python -m pytest tests/test_scoring.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))

from scoring.engine import (  # noqa: E402
    ScoringContext,
    ScoringCounterSignal,
    ScoringSignal,
    score_conversation,
)
from scoring.taxonomy import BAND_CRITICAL, BAND_LOW, BAND_MEDIUM  # noqa: E402


def sig(label, severity, confidence, tier=2, idx=None, pos=None):
    return ScoringSignal(
        type=label,
        severity=severity,
        confidence=confidence,
        tier=tier,
        message_index=idx,
        position_s=pos,
    )


# ------------------------------------------------------------------ Example 1
def test_example_1_critical_bank_otp():
    """Base 53.02 +chronology +corroboration -uncertainty -> ~76.4 Critical."""
    result = score_conversation(
        signals=[
            sig("bank_impersonation", 4, 0.92, idx=2),
            sig("otp_harvesting", 5, 0.97, idx=4),
            sig("urgency_pressure", 3, 0.85, idx=5),
            sig("secrecy_request", 2, 0.80, idx=5),
            sig("authority_claim", 3, 0.80, idx=3),
        ],
        context=ScoringContext(),
    )
    assert abs(result.score - 76.4) <= 0.5
    assert result.band == BAND_CRITICAL
    assert abs(result.positive_total - 53.02) <= 0.05
    assert result.chronology_applied
    assert result.corroboration_applied


# ------------------------------------------------------------------ Example 2
def test_example_2_safe_counters_clamp_to_zero():
    """investment_pitch + legitimate OTP counter -> total negative -> Low."""
    result = score_conversation(
        signals=[sig("investment_pitch", 2, 0.5, idx=6)],
        counters=[ScoringCounterSignal("legitimate_otp_context", 0.9)],
    )
    assert abs(result.positive_total - 2.40) <= 0.05
    assert abs(result.negative_total - (-10.80)) <= 0.05
    assert result.score == 0
    assert result.band == BAND_LOW


# ------------------------------------------------------------------ Example 3
def test_example_3_tier1_only_caps_at_medium_via_floor():
    """Tier-1 only: raw 24.72 -> cap 24 -> unknown caller + Family A -> floor 25 Medium."""
    result = score_conversation(
        signals=[
            sig("otp_harvesting", 5, 0.60, tier=1, idx=40),
            sig("bank_impersonation", 3, 0.70, tier=1, idx=2),
        ],
        context=ScoringContext(unknown_caller=True),
    )
    assert abs(result.positive_total - 24.72) <= 0.05
    assert result.tier1_cap_applied
    assert result.context_floor_applied
    assert result.score == 25
    assert result.band == BAND_MEDIUM


def test_tier1_only_never_exceeds_medium_ceiling_without_floor():
    """Even absurd Tier-1 volume stays <= 24 when no floor applies."""
    signals = [sig("otp_harvesting", 5, 0.99, tier=1, idx=i) for i in range(12)]
    signals += [sig("credential_request", 5, 0.99, tier=1, idx=20 + i) for i in range(12)]
    result = score_conversation(signals)
    assert result.tier1_cap_applied
    assert result.score <= 24


def test_ratchet_score_falls_at_most_five_per_cycle():
    base = [
        sig("bank_impersonation", 4, 0.92, idx=2),
        sig("otp_harvesting", 5, 0.97, idx=4),
        sig("urgency_pressure", 3, 0.85, idx=5),
        sig("secrecy_request", 2, 0.80, idx=5),
        sig("authority_claim", 3, 0.80, idx=3),
    ]
    high = score_conversation(base)
    assert high.score >= 75

    # scammer switches to small talk: engine sees almost nothing
    calm = score_conversation(
        [sig("trust_acceleration", 1, 0.30, idx=30)],
        previous_displayed_score=high.score,
    )
    assert calm.score >= high.score - 5.0
    assert calm.ratcheted_from == high.score


def test_ratchet_does_not_limit_rises():
    low = score_conversation([sig("urgency_pressure", 2, 0.4, idx=0)])
    spike = score_conversation(
        [
            sig("bank_impersonation", 4, 0.92, idx=2),
            sig("otp_harvesting", 5, 0.97, idx=4),
            sig("urgency_pressure", 3, 0.85, idx=5),
            sig("secrecy_request", 2, 0.80, idx=5),
            sig("authority_claim", 3, 0.80, idx=3),
        ],
        previous_displayed_score=low.score,
    )
    assert spike.score > low.score + 50


def test_counter_signal_total_capped_at_minus_fifteen():
    counters = [
        ScoringCounterSignal("legitimate_otp_context", 1.0),   # -12
        ScoringCounterSignal("known_contact_context", 1.0),    # -8
        ScoringCounterSignal("verifiable_identity", 1.0),      # -8  => -28 uncapped
    ]
    result = score_conversation([sig("urgency_pressure", 3, 0.9, idx=0)], counters)
    assert result.negative_total == -15.0


def test_frequency_bonus_eight_percent_capped_thirty():
    single = score_conversation([sig("otp_harvesting", 5, 0.90, idx=0)])
    twice = score_conversation(
        [sig("otp_harvesting", 5, 0.90, idx=0), sig("otp_harvesting", 5, 0.85, idx=9)]
    )
    expected_bonus = single.positive_total * 0.08
    assert abs((twice.positive_total - single.positive_total) - expected_bonus) <= 0.01

    many = score_conversation(
        [sig("otp_harvesting", 5, 0.90, idx=i * 10) for i in range(10)]
    )
    # 9 repeats would be +72% uncapped; must cap at +30%
    assert abs(many.positive_total - single.positive_total * 1.30) <= 0.01


def test_cross_channel_modifier():
    without = score_conversation(
        [
            sig("bank_impersonation", 4, 0.92, idx=2, pos=10.0),
            sig("otp_harvesting", 5, 0.97, idx=4, pos=50.0),
        ]
    )
    with_mod = score_conversation(
        [
            sig("bank_impersonation", 4, 0.92, idx=2, pos=10.0),
            sig("otp_harvesting", 5, 0.97, idx=4, pos=50.0),
        ],
        context=ScoringContext(cross_channel_otp=True),
    )
    assert with_mod.score - without.score == 10.0
    assert with_mod.cross_channel_applied


def test_chronology_voice_window_120_seconds():
    inside = score_conversation(
        [
            sig("bank_impersonation", 4, 0.92, pos=100.0),
            sig("otp_harvesting", 5, 0.97, pos=210.0),
        ]
    )
    outside = score_conversation(
        [
            sig("bank_impersonation", 4, 0.92, pos=0.0),
            sig("otp_harvesting", 5, 0.97, pos=200.0),
        ]
    )
    assert inside.chronology_applied
    assert not outside.chronology_applied
    assert inside.score - outside.score == 10.0


def test_unknown_caller_floor_requires_family_a():
    floored = score_conversation(
        [sig("urgency_pressure", 5, 0.99, idx=0)],
        context=ScoringContext(unknown_caller=True),
    )
    assert not floored.context_floor_applied

    family_a_only = score_conversation(
        [sig("courier_impersonation", 1, 0.30, idx=0)],
        context=ScoringContext(unknown_caller=True),
    )
    assert family_a_only.context_floor_applied
    assert family_a_only.score == 25
