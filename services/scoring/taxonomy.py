"""Canonical 38-label taxonomy — Build Bible Appendix A, VERBATIM.

Do not rename labels, do not add top-level labels. Weights are the single
source of truth for the deterministic scorer (services.scoring.engine).
"""

from dataclasses import dataclass


FAMILY_A_IMPERSONATION = "A"
FAMILY_B_FINANCIAL_CREDENTIAL = "B"
FAMILY_C_MANIPULATION_BEHAVIOUR = "C"
FAMILY_D_CONTEXT_SAFE_COUNTER = "D"


@dataclass(frozen=True)
class LabelDef:
    name: str
    weight: float
    family: str
    fires_when: str


LABELS: dict[str, LabelDef] = {}


def _register(name: str, weight: float, family: str, fires_when: str) -> None:
    LABELS[name] = LabelDef(name=name, weight=weight, family=family, fires_when=fires_when)


# ---------------------------------------------------------------- Family A — Impersonation (10)
_register("bank_impersonation", 16, FAMILY_A_IMPERSONATION, "claims to be any bank / bank fraud department")
_register("government_impersonation", 16, FAMILY_A_IMPERSONATION, "FBR, NADRA, FIA, police, court")
_register("wallet_impersonation", 15, FAMILY_A_IMPERSONATION, "JazzCash, Easypaisa, Raast, SadaPay, NayaPay")
_register("family_impersonation", 14, FAMILY_A_IMPERSONATION, '"your son/brother", stuck abroad')
_register("telecom_impersonation", 12, FAMILY_A_IMPERSONATION, "Jazz/Telenor/Ufone/Zong/PTA")
_register("utility_impersonation", 12, FAMILY_A_IMPERSONATION, "electricity/gas disconnection")
_register("tech_support_impersonation", 12, FAMILY_A_IMPERSONATION, "fake IT/Microsoft/bank app support")
_register("employer_recruiter_impersonation", 12, FAMILY_A_IMPERSONATION, "fake HR/interview")
_register("courier_impersonation", 10, FAMILY_A_IMPERSONATION, "fake parcel/customs fee")
_register("authority_claim", 8, FAMILY_A_IMPERSONATION, "generic official-sounding role/case number claims")

# ------------------------------------------------- Family B — Financial & credential (10)
_register("otp_harvesting", 30, FAMILY_B_FINANCIAL_CREDENTIAL, "asks for OTP / verification / one-time code")
_register("credential_request", 28, FAMILY_B_FINANCIAL_CREDENTIAL, "password, PIN, CVV, full card number, CNIC + answers")
_register("payment_request_disguised_as_receipt", 24, FAMILY_B_FINANCIAL_CREDENTIAL, '"I sent money by mistake, return it" / request-as-receipt')
_register("account_number_request", 20, FAMILY_B_FINANCIAL_CREDENTIAL, 'asks for IBAN/account "to send you money"')
_register("upfront_fee_demand", 18, FAMILY_B_FINANCIAL_CREDENTIAL, 'job deposit, registration, "refundable" fee')
_register("payment_redirection", 16, FAMILY_B_FINANCIAL_CREDENTIAL, "pay to a different account/link/person")
_register("suspicious_link", 15, FAMILY_B_FINANCIAL_CREDENTIAL, "shortened/odd links, fake payment pages")
_register("remittance_request", 14, FAMILY_B_FINANCIAL_CREDENTIAL, "urgent money transfer/wire abroad")
_register("investment_pitch", 12, FAMILY_B_FINANCIAL_CREDENTIAL, "guaranteed returns, crypto doubling, trading groups")
_register("prize_lottery_claim", 12, FAMILY_B_FINANCIAL_CREDENTIAL, 'winnings requiring a "processing" step')

# ------------------------------------------------- Family C — Manipulation & behaviour (14)
_register("threat_intimidation", 14, FAMILY_C_MANIPULATION_BEHAVIOUR, "arrest, account block, legal action, fines")
_register("isolation_pressure", 12, FAMILY_C_MANIPULATION_BEHAVIOUR, "don't consult family/bank/branch")
_register("verification_avoidance", 12, FAMILY_C_MANIPULATION_BEHAVIOUR, "refuses callback on the official number")
_register("escalation_after_hesitation", 12, FAMILY_C_MANIPULATION_BEHAVIOUR, 'anger, guilt-trip, "colleague" joins')
_register("urgency_pressure", 10, FAMILY_C_MANIPULATION_BEHAVIOUR, 'countdowns, "within 10 minutes", "today only"')
_register("secrecy_request", 10, FAMILY_C_MANIPULATION_BEHAVIOUR, '"don\'t tell anyone"')
_register("emotional_exploitation", 10, FAMILY_C_MANIPULATION_BEHAVIOUR, "fear, pity, love-bombing pressure")
_register("rapid_intimacy", 9, FAMILY_C_MANIPULATION_BEHAVIOUR, "unusual fast romantic/close rapport")
_register("false_credibility_props", 9, FAMILY_C_MANIPULATION_BEHAVIOUR, "fake employee IDs, case numbers, screenshots")
_register("trust_acceleration", 8, FAMILY_C_MANIPULATION_BEHAVIOUR, "unusually fast trust-building")
_register("platform_migration", 8, FAMILY_C_MANIPULATION_BEHAVIOUR, "push to move off-platform / to WhatsApp")
_register("boundary_probing", 7, FAMILY_C_MANIPULATION_BEHAVIOUR, "small escalating asks")
_register("persistence_repetition", 6, FAMILY_C_MANIPULATION_BEHAVIOUR, "re-asks after refusal")
_register("unsolicited_contact_origin", 6, FAMILY_C_MANIPULATION_BEHAVIOUR, "cold contact from unknown number")

# ------------------------------------------- Family D — Context-safe counter-signals (4, negative)
_register("legitimate_otp_context", -12, FAMILY_D_CONTEXT_SAFE_COUNTER, "OTP arrives for a login/payment the USER just initiated")
_register("known_contact_context", -8, FAMILY_D_CONTEXT_SAFE_COUNTER, "counterpart is a saved/trusted contact")
_register("verifiable_identity", -8, FAMILY_D_CONTEXT_SAFE_COUNTER, "caller offers a callback on the official listed number")
_register("platform_official_channel", -6, FAMILY_D_CONTEXT_SAFE_COUNTER, "sender matches an official bank short code in bank_directory")

assert len(LABELS) == 38, f"taxonomy must hold exactly 38 labels, has {len(LABELS)}"

SCAM_LABELS = {n for n, d in LABELS.items() if d.weight > 0}
COUNTER_LABELS = {n for n, d in LABELS.items() if d.weight < 0}

STAGES = [
    "contact",
    "credibility",
    "rapport",
    "verification_avoidance",
    "isolation",
    "boundary_probing",
    "opportunity_crisis",
    "urgency",
    "credential_or_financial_request",
    "escalation",
]

LANGUAGES = ["english", "roman_urdu", "urdu", "mixed"]

BAND_LOW = "low"
BAND_MEDIUM = "medium"
BAND_HIGH = "high"
BAND_CRITICAL = "critical"

# Bible Section 15.4 bands
BANDS = {
    BAND_LOW: (0, 24),
    BAND_MEDIUM: (25, 49),
    BAND_HIGH: (50, 74),
    BAND_CRITICAL: (75, 100),
}


def band_for_score(score: float) -> str:
    """Low 0–24 | Medium 25–49 | High 50–74 | Critical 75–100."""
    s = max(0.0, min(100.0, score))
    if s <= 24:
        return BAND_LOW
    if s <= 49:
        return BAND_MEDIUM
    if s <= 74:
        return BAND_HIGH
    return BAND_CRITICAL


SAFE_ACTIONS_BY_BAND = {
    BAND_LOW: [],
    BAND_MEDIUM: [],
    BAND_HIGH: ["verify_independently"],
    BAND_CRITICAL: ["hang_up", "call_bank_official", "report", "block", "mock_freeze"],
}
