"""Tier-1 deterministic rules engine — Build Bible Section 3 + Section 10.

Instant (<150 ms target) keyword/regex tier running on-device (Android mirror)
and server-side (voice path + dashboard mirror). English + Urdu script +
Roman Urdu. Tier-1 NEVER blocks a call and NEVER alone pushes the score past
Medium — that guarantee lives in the scorer's Tier-1-only cap, not here.

Every hit carries the exact matched substring as `quote` so evidence cards can
be traced back to the conversation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .engine import ScoringSignal


@dataclass(frozen=True)
class Tier1Rule:
    label: str
    severity: int
    confidence: float
    patterns: tuple[str, ...]


# ----------------------------------------------------------------------------------
# Lexicon — top red-flag terms across three scripts (Bible Section 10).
# Confidence anchors come from Section 15.5 example 3 (otp T1 = 0.60, bank = 0.70).
# ----------------------------------------------------------------------------------
RULES: tuple[Tier1Rule, ...] = (
    # ---------------- Family B — financial & credential ----------------
    Tier1Rule("otp_harvesting", 5, 0.60, (
        r"\botp\b", r"one[- ]time (?:password|code|pin)", r"verification code",
        r"\bverify(?:ing)? code\b", r"security code", r"\bcvv\b",
        r"کوڈ بتا", r"وریفکیشن کوڈ", r"او ٹی پی", r"اوٹیپی", r"کوڈ سناؤ",
        # whisper-tolerant spellings (voice path garbles: آتی پی، کور باتا)
        r"[اآ]و? ?[ٹت]ی ?پی", r"کو[ڑر] ?بتا",
        r"code batao?\b", r"code sunao", r"otp (?:batao|sunao|share|bata|deen)",
        r"code (?:kya hai|bhejo|bata)", r"pin code batao",
    )),
    Tier1Rule("credential_request", 5, 0.65, (
        r"\bpassword\b", r"\bpin\b.{0,20}\b(batao|share|confirm)\b",
        r"full card number", r"complete card number", r"card number (?:do|bata)",
        r"cnic.{0,25}(?:number|photo|answer)", r"mother maiden name",
        r"password (?:batao|bata|share)", r"پاس ورڈ بتا", r"کارڈ نمبر",
    )),
    Tier1Rule("payment_request_disguised_as_receipt", 4, 0.70, (
        r"(?:sent|sent you) money by mistake", r"mistakenly sent", r"ghalti se (?:paisa|paise|paisay)",
        r"غلطی سے پیسے", r"wapsi (?:kar do|bhejo)", r"return the (?:money|payment)",
        r"wapas kar do", r"galti se transfer",
    )),
    Tier1Rule("account_number_request", 4, 0.70, (
        r"\bibAN\b", r"account number.{0,30}(?:send|bhejo|batao|do|confirm|dein)",
        r"account number dein", r"اکاؤنٹ نمبر", r"حساب نمبر",
        r"account (?:number )?(?:do|dena|batao|confirm)", r"iban (?:do|bhejo|batao)",
    )),
    Tier1Rule("upfront_fee_demand", 4, 0.70, (
        r"registration fee", r"processing fee", r"security deposit",
        r"advance (?:fee|payment|deposit)", r"refundable (?:fee|deposit|charges)",
        r"fee jama karo", r"fee jama karein", r"فیس جمع", r"پہلے پیسے",
        r"pehle (?:paisay|paise) (?:bhejo|jama)",
    )),
    Tier1Rule("payment_redirection", 4, 0.70, (
        r"(?:pay|transfer|send).{0,40}(?:this|following|different) (?:account|number)",
        r"doosre account", r"dusre account par bhejo", r"دوسرے اکاؤنٹ",
        r"is number par (?:bhejo|transfer)", r"personal account",
    )),
    Tier1Rule("suspicious_link", 4, 0.75, (
        r"bit\.ly/", r"tinyurl\.com", r"t\.co/", r"\bcutt\.ly\b", r"\bgoo\.gl\b",
        r"is\.gd", r"shorturl", r"click (?:here|this link)", r"لنک کھولو",
        r"link (?:kholo|open karo|par click)", r"kyc[- ]?update", r"[a-z0-9-]+\.(?:xyz|top|icu|club)\b",
    )),
    Tier1Rule("remittance_request", 4, 0.65, (
        r"western union", r"money ?gram", r"hundi", r"wire transfer",
        r"videsh (?:se|ko)", r"bahar (?:bhejo|transfer)", r"بیرون ملک",
        r"urgent transfer abroad",
    )),
    Tier1Rule("investment_pitch", 2, 0.60, (
        r"guaranteed (?:returns|profit)", r"double your money", r"paisa double",
        r"daily profit", r"crypto (?:investment|trading group|doubling)",
        r"forex (?:group|signals?)", r"trading group join", r"سرمایہ کاری",
        r"munafa", r"profit pakka", r"100% (?:return|profit|guarantee)",
    )),
    Tier1Rule("prize_lottery_claim", 3, 0.70, (
        r"you(?:'| a)?ve won", r"you have won", r"\blottery\b", r"lucky draw",
        r"\bprize\b.{0,30}(?:won|claim|jeeta)", r"jeet.? gaye", r"انعام",
        r"inam (?:nikla|hai)", r"prize claim karo", r"easy paisa lottery",
    )),
    # ---------------- Family A — impersonation ----------------
    Tier1Rule("bank_impersonation", 4, 0.70, (
        r"bank (?:fraud department|security department|verification team)",
        r"(?:apna|hbl|ubl|meezan|metro commercial|faisal) bank",  # fictional demo banks only
        r"fraud department", r"suspicious (?:transaction|activity) on your account",
        r"bank se baat karo", r"بینک کا فراڈ ڈیپارٹمنٹ", r"بینک افسر",
        r"main bank se bol raha", r"hum apnabank se",
        # whisper-tolerant Urdu (voice path): اپنا بینک، مشکوپ/مشکوک، فراڈ ڈیپارٹمنٹ
        r"اپنا بینک", r"مشکو[کپق]", r"فراڈ? ?ڈیپارٹمنٹ",
    )),
    Tier1Rule("government_impersonation", 4, 0.70, (
        r"\bfbr\b", r"\bnadra\b", r"\bfia\b", r"cyber ?crime", r"police (?:station|department)",
        r"court (?:notice|warrant|summons)", r" arrest warrant", r"گرفتاری",
        r"وارنٹ", r"کیس نمبر", r"fbr se notice", r"nadra (?:office|block)",
    )),
    Tier1Rule("wallet_impersonation", 4, 0.70, (
        r"easypaisa", r"jazz ?cash", r"\braast\b", r"sada ?pay", r"naya ?pay",
        r"easypaisa (?:agent|team|verify)", r"جاز کیش", r"ایزی پیسہ",
    )),
    Tier1Rule("family_impersonation", 4, 0.60, (
        r"your (?:son|brother|daughter|sister)", r"mera beta", r"apna beta",
        r"stuck abroad", r"phansi (?:me|main)", r"میرا بیٹا", r"بھائی کہ رہا",
        r"main (?:bhai|beta) bol raha", r"emergency (?:hai|mein) mujhe",
    )),
    Tier1Rule("telecom_impersonation", 3, 0.70, (
        r"\bjazz\b.{0,20}(?:team|offer|verify)", r"telenor", r"ufone", r"\bzong\b",
        r"\bpta\b.{0,20}(?:notice|block|verify)", r"sim (?:block|verify|expire)",
        r"سِم بلاک",
    )),
    Tier1Rule("utility_impersonation", 3, 0.70, (
        r"electricity (?:connection)?.{0,20}disconnect", r"bijli (?:kat)? ?ja ?egi",
        r"gas disconnect", r"wAPDA", r"k-electric", r"bill (?:(?:nahi|not) )?(?:clear|hua)",
        r"بجلی کاٹ", r"کنکشن کاٹ",
    )),
    Tier1Rule("tech_support_impersonation", 3, 0.65, (
        r"(?:microsoft|windows|google pay|whatsapp) support", r"technical support team",
        r"your (?:device|phone) (?:is )?(?:infected|hacked|compromised)",
        r"virus (?:detect|found)", r"aap ka phone hack",
    )),
    Tier1Rule("employer_recruiter_impersonation", 3, 0.60, (
        r"(?:hr |recruitment|interview) (?:manager|team).{0,30}(?:selected|shortlisted)",
        r"work from home (?:job|earn)", r"online job.{0,20}(?:daily|earning)",
        r"job (?:lagi|select) ", r"نوکری مل گئی",
    )),
    Tier1Rule("courier_impersonation", 3, 0.65, (
        r"\btcs\b|\bledex\b|\bdhl\b|\bfe ?dex\b", r"parcel (?:customs|held|fee)",
        r"customs (?:duty|clearance) fee", r"parcel (?:rok|phasa) ", r"پارسل",
    )),
    Tier1Rule("authority_claim", 3, 0.60, (
        r"\bcase (?:number|id|#)\b", r"officer ID", r"badge number", r"official record",
        r"case darj ", r"complaint number", r"verification officer",
    )),
    # ---------------- Family C — manipulation & behaviour ----------------
    Tier1Rule("threat_intimidation", 4, 0.70, (
        r"(?:will be|ho jay?gi|ho jaye ?gi).{0,30}(?:arrested|blocked|frozen|closed)",
        r"block hone (?:wala|wali|walay)", r"legal action", r"police ke hawale",
        r"account block", r"jail", r"greftar ", r"خبردار", r"قید", r"salakhkhanay",
        r"permanent(ly)? block", r"criminal charges",
        # whisper-tolerant Urdu (voice path): بلک ہو / اکاؤنٹ بلاک
        r"بل[اک] ہو", r"اکاؤنٹ? بل[اک]",
    )),
    Tier1Rule("isolation_pressure", 3, 0.70, (
        r"don(?:'|no)?t tell (?:anyone|anybody|them|your (?:family|parents|husband))",
        r"kisi ko (?:na|mat) batana", r"chup ?ke (?:rakhna|rakho)", r"baat na karna kisi se",
        r"کسی کو نہ بتانا", r"خفیہ رکھو", r"family ko mat batana",
        r"do not (?:consult|inform) (?:your bank|the branch|anyone)",
    )),
    Tier1Rule("verification_avoidance", 4, 0.70, (
        r"do not call the bank", r"no need to verify", r"main line se call (?:mat )?karna",
        r"callback ki zaroorat nahi", r"trust me, no callback", r"bank ko call (?:mat )?karo",
        r"main hi sab verify", r"official number par call mat",
    )),
    Tier1Rule("urgency_pressure", 3, 0.65, (
        r"within \d+ (?:minutes|mins|hours|hours)", r"right now", r"abhi (?:hi|foran|turant)",
        r"turant", r"foran", r"jaldi (?:karo|karen|bhejo)", r"today only", r"last chance",
        r"time (?:nak?hr?ta|khatam) ho", r"فوراً", r"فوری", r"جلدی کرو", r"ابھی",
        r"\bdies? today\b", r"before \d+ ?(?:pm|am|o'?clock)",
    )),
    Tier1Rule("secrecy_request", 2, 0.70, (
        r"keep (?:this )?(?:secret|confidential)", r"confidential (?:call|matters)",
        r"raaz (?:rakhna|rakho)", r"chupa (?:lo|na|ke rakhna)", r"خفیہ",
        r"secret rakhna", r"yeh baat sirf hum",
    )),
    Tier1Rule("emotional_exploitation", 3, 0.60, (
        r"(?:i am|main).{0,20}(?:dying|mar raha|bimar)", r"hospital (?:me|main)",
        r"bachao", r"mujhe bacha", r"please help (?:me|mere)", r"mera haal",
        r"بچاؤ", r"مریض", r"رحم کرو", r"love you.{0,20}(?:send|bhejo|help)",
        r"if you (?:love|care about) me",
    )),
    Tier1Rule("platform_migration", 3, 0.60, (
        r"(?:move|switch|continue) (?:to|on) whatsapp", r"whatsapp par (?:aao|message|baat)",
        r"telegram par aao", r"text me on whatsapp", r"واٹس ایپ پر آؤ",
    )),
    Tier1Rule("false_credibility_props", 3, 0.65, (
        r"(?:my|employee|id) ?(?:card|id) number.{0,15}\d{4,}", r"see my id card",
        r"screenshot (?:dekho|check|attached)", r"official stamp",
        r"id card (?:number|photo) bhejo", r"id card (?:number|photo)",
        r"ملازمت کارڈ", r"sanad",
    )),
)

# Self-initiated OTP phrasing — the only Tier-1 counter-signal detectable from text.
COUNTER_RULES: tuple[Tier1Rule, ...] = (
    Tier1Rule("legitimate_otp_context", 1, 0.70, (
        r"use (?:this|the) code to (?:log ?in|confirm|complete|verify)[a-z ]{0,15}(?:your own|yourself)",
        r"code (?:for|to verify) your (?:own )?(?:login|signup|registration)",
        r"otp (?:aap khud ne mangwaya|for your (?:own )?login)",
        r"code (?:jo )?aap ne (?:khud )?(?:request|mangwaya)",
    )),
)


def normalize(text: str) -> str:
    """NFC-normalize + strip zero-width / directional marks common in WhatsApp exports."""
    text = unicodedata.normalize("NFC", text)
    for ch in ("\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u2066", "\u2067", "\u2068", "\u2069", "\ufeff"):
        text = text.replace(ch, "")
    return text


_COMPILED: list[tuple[Tier1Rule, list[re.Pattern[str]]]] = [
    (rule, [re.compile(p, re.IGNORECASE | re.UNICODE) for p in rule.patterns])
    for rule in RULES
]
_COMPILED_COUNTERS: list[tuple[Tier1Rule, list[re.Pattern[str]]]] = [
    (rule, [re.compile(p, re.IGNORECASE | re.UNICODE) for p in rule.patterns])
    for rule in COUNTER_RULES
]


def _run(text: str, compiled, tier: int, message_index: int | None = None,
         position_s: float | None = None) -> list[ScoringSignal]:
    hits: list[ScoringSignal] = []
    seen_labels: set[str] = set()
    for rule, patterns in compiled:
        if rule.label in seen_labels:
            continue  # one instance per label per message — repeats across messages are what count
        for pattern in patterns:
            m = pattern.search(text)
            if not m:
                continue
            seen_labels.add(rule.label)
            hits.append(
                ScoringSignal(
                    type=rule.label,
                    severity=rule.severity,
                    confidence=rule.confidence,
                    tier=tier,
                    message_index=message_index,
                    position_s=position_s,
                )
            )
            break
    return hits


def run_tier1_message(
    text: str,
    message_index: int | None = None,
    position_s: float | None = None,
) -> list[ScoringSignal]:
    """Tier-1 scan of ONE normalized message/transcript segment."""
    cleaned = normalize(text)
    return _run(cleaned, _COMPILED, tier=1, message_index=message_index, position_s=position_s)


def run_tier1_conversation(messages: list[str]) -> list[ScoringSignal]:
    """Tier-1 scan across a whole conversation; index i message -> message_index i."""
    hits: list[ScoringSignal] = []
    for i, text in enumerate(messages):
        hits.extend(run_tier1_message(text, message_index=i))
    return hits


def run_counter_rules(
    text: str,
    message_index: int | None = None,
    position_s: float | None = None,
) -> list[ScoringSignal]:
    cleaned = normalize(text)
    return _run(cleaned, _COMPILED_COUNTERS, tier=1, message_index=message_index, position_s=position_s)
