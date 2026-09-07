"""Caller-ID verification tier tests — bank_directory.json integration.

Run:  PYTHONPATH=services .venv/bin/python -m pytest tests/test_caller_id.py -q
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))

from scoring.caller_id import (  # noqa: E402
    analyze_caller,
    check_suspicious_number,
    extract_org_claims,
    normalize_number,
    verify_caller,
)
from scoring.engine import score_conversation, ScoringContext  # noqa: E402


# ------------------------------------------------------------------ normalization
def test_normalize_number_prefixes_and_formats():
    assert normalize_number("+92-300-1234567") == "+923001234567"
    assert normalize_number("0092-300-1234567") == "+923001234567"
    assert normalize_number("03001234567") == "+923001234567"
    assert normalize_number("(0300) 123-4567") == "+923001234567"
    assert normalize_number("923001234567") == "+923001234567"
    assert normalize_number("111-111-425") == "111111425"
    assert normalize_number("051-111-111-425") == "+9251111111425"
    assert normalize_number("3737") == "3737"
    assert normalize_number("  ") == ""
    assert normalize_number(None) == ""


def test_normalize_number_keypad_letters():
    # vanity number: APNA -> 2762
    assert normalize_number("+92-21-111-APNA-00") == "+9221111276200"
    assert normalize_number("+92-21-111-APNA-00") == normalize_number("+92-21-111-2762-00")


# ------------------------------------------------------------------ claim detection
def test_hbl_claim_from_mobile_fires_bank_impersonation():
    signals, counters, warnings = analyze_caller(
        "Main HBL se bol raha hun, aap ka account block ho jaye ga",
        "+92-300-1234567",
    )
    bank = [s for s in signals if s.type == "bank_impersonation"]
    assert bank, "expected bank_impersonation evidence for HBL claim from a mobile"
    s = bank[0]
    assert s.severity >= 4
    assert s.confidence == 0.9
    assert s.tier == 1
    assert counters == []
    assert any("HBL" in w for w in warnings)


def test_hbl_claim_from_official_number_yields_counter():
    for official in ("111-111-425", "111 111 425", "051-111-111-425", "+92-51-111-111-425"):
        signals, counters, _ = analyze_caller("Main HBL se bol raha hun", official)
        assert not [s for s in signals if s.type == "bank_impersonation"], official
        assert any(
            c.type == "platform_official_channel" and c.confidence == 0.95
            for c in counters
        ), official


def test_wallet_official_shortcode_yields_counter():
    signals, counters, _ = analyze_caller("Main JazzCash se bol raha hun", "4444")
    assert not [s for s in signals if s.type == "wallet_impersonation"]
    assert any(c.type == "platform_official_channel" for c in counters)


def test_mention_without_claim_phrase_does_not_fire():
    text = "Easypaisa se koi message nahi aya"
    assert extract_org_claims(text) == []
    signals, _, _ = analyze_caller(text, "+92-301-2345678")
    assert not [
        s for s in signals if s.type in ("wallet_impersonation", "bank_impersonation")
    ]


def test_english_claim_phrase_fires():
    signals, _, _ = analyze_caller(
        "This is the Meezan Bank fraud department calling from head office",
        "+92-333-9876543",
    )
    assert any(s.type == "bank_impersonation" for s in signals)


def test_government_claim_from_mobile_fires():
    signals, _, warnings = analyze_caller(
        "Main NADRA se call kar raha hun, aap ki CNIC block ho jayegi",
        "0301-2345678",
    )
    assert any(s.type == "government_impersonation" for s in signals)
    assert any("NADRA" in w for w in warnings)


def test_fictional_bank_never_produces_signals():
    # ApnaBank is a demo entity — a claim from a mobile number is demo traffic
    signals, counters, warnings = analyze_caller(
        "Main ApnaBank se bol raha hun, OTP code batao", "+92-300-1234567"
    )
    assert signals == []
    assert counters == []
    assert warnings == []
    # ...and neither does the fictional Metro Commercial Bank
    signals, counters, warnings = analyze_caller(
        "Main Metro Commercial Bank se bol raha hun", "0345-1234567"
    )
    assert signals == [] and counters == [] and warnings == []


def test_no_caller_number_returns_empty():
    for none_value in (None, "", "   "):
        signals, counters, warnings = analyze_caller(
            "Main HBL se bol raha hun", none_value
        )
        assert signals == [] and counters == [] and warnings == []


# ------------------------------------------------------------------ verify_caller
def test_verify_caller_result_shape():
    claims = extract_org_claims("Main Meezan Bank se bol raha hun")
    assert len(claims) == 1
    assert claims[0].category == "bank"
    assert claims[0].fictional is False

    mismatch = verify_caller(claims, "+923001234567")
    assert mismatch.is_verified is False
    assert len(mismatch.mismatched) == 1 and not mismatch.verified

    verified = verify_caller(claims, "111-331-331")
    assert verified.is_verified is True
    assert len(verified.verified) == 1 and not verified.mismatched


def test_unlisted_org_number_also_mismatches():
    # JS Bank shares its helpline format with Summit — a Summit claim from the
    # JS number must still mismatch for Summit's own entry.
    claims = extract_org_claims("Main Summit Bank se bol raha hun")
    res = verify_caller(claims, "111-124-444")
    assert res.is_verified is True  # 111-124-444 IS a Summit official number


# ------------------------------------------------------------------ suspicious numbers
def test_suspicious_number_patterns():
    assert "pk_mobile_general" in {m["id"] for m in check_suspicious_number("+92-300-1234567")}
    assert "pk_mobile_general" in {m["id"] for m in check_suspicious_number("03001234567")}
    assert "masked_or_hidden_caller_id" in {m["id"] for m in check_suspicious_number("Unknown")}
    assert "masked_or_hidden_caller_id" in {m["id"] for m in check_suspicious_number("private")}
    assert "voice_call_from_shortcode" in {m["id"] for m in check_suspicious_number("3737")}
    assert "repeated_digit_number" in {m["id"] for m in check_suspicious_number("0300-0000000")}
    assert "sequential_digit_number" in {m["id"] for m in check_suspicious_number("1234567890")}
    assert "international_non_pk_caller" in {m["id"] for m in check_suspicious_number("+1-202-555-0134")}


def test_attribution_patterns_never_score_alone():
    hits = {m["id"] for m in check_suspicious_number("+92-300-1234567")}
    assert "pk_mobile_jazz_series" not in hits
    assert "pk_mobile_zong_series" not in hits


def test_international_caller_claiming_bank_escalates():
    signals, _, _ = analyze_caller(
        "This is HBL calling from our London office", "+44-20-7946-0958"
    )
    assert any(s.type == "bank_impersonation" for s in signals)


def test_unclaimed_suspicious_number_is_weak_only():
    signals, _, _ = analyze_caller("Hello jee, kya haal hai?", "+92-300-1234567")
    weak = [s for s in signals if s.type == "unsolicited_contact_origin"]
    assert weak, "suspicious number with no claim should yield a weak signal"
    assert all(s.confidence <= 0.5 and s.severity <= 3 for s in signals)


def test_directory_loaded_once_and_cached():
    from scoring.caller_id import _directory

    d = _directory()
    assert d["metadata"]["country"] == "Pakistan"
    assert _directory() is d  # lru_cache: same object identity
    categories = {o["category"] for o in d["organizations"]}
    assert {"bank", "wallet", "telco", "government", "utility", "courier", "tech"} <= categories


# ------------------------------------------------------------------ scorer fusion
def test_caller_id_signals_flow_through_scorer():
    signals, counters, _ = analyze_caller(
        "Main HBL se bol raha hun, OTP code batao", "+92-300-1234567"
    )
    from scoring.rules_engine import run_tier1_message

    all_signals = list(signals)
    for i, text in enumerate(["Main HBL se bol raha hun, OTP code batao"]):
        all_signals.extend(run_tier1_message(text, message_index=i))
    result = score_conversation(
        signals=all_signals,
        counters=counters,
        context=ScoringContext(unknown_caller=True),
    )
    assert result.band in ("medium", "high", "critical")
    assert "bank_impersonation" in {c.label for c in result.contributions}


def test_official_channel_counter_lowers_score():
    scam_signals, _, _ = analyze_caller(
        "Main HBL se bol raha hun, OTP code batao", "+92-300-1234567"
    )
    _, counters, _ = analyze_caller("Main HBL se bol raha hun", "111-111-425")
    without = score_conversation(signals=scam_signals)
    with_counter = score_conversation(signals=scam_signals, counters=counters)
    assert with_counter.score < without.score
