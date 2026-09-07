"""Synthetic labelled-utterance corpus for the trained taxonomy tier.

The Build Bible's golden set (60 conversations) is an *evaluation* asset - far
too small to train on, and training on it would invalidate every number
scripts/eval.py prints. So we generate training data instead.

Generation strategy
-------------------
1. Each Appendix-A label owns a bank of templates with {slot} placeholders:
   a Roman-Urdu/English bank (TEMPLATES) and a native Urdu-script bank
   (URDU_TEMPLATES). ~35% of renders come from the Urdu bank, because
   evaluation showed Urdu-script conversations scoring poorly on a corpus
   the model had only ever seen in Roman script.
2. Slots expand to realistic Pakistani-context fillers (fictional banks only,
   per Bible §17). A few slot values are Urdu-script ("پچاس ہزار", "او ٹی پی")
   because real Urdu texting mixes scripts freely.
3. Every rendered string then passes through Roman-Urdu orthographic drift
   ("paisay"/"paise"/"pesay", "batao"/"btao"/"bata do") and light keyboard
   noise. This is what teaches the model to generalise past fixed spellings.
4. ~35% of samples are *composed* - two clauses from different labels joined
   into one utterance carrying both labels. Real scam lines bundle an identity
   claim with an urgency cue; the model has to handle multi-label input.
5. Benign utterances (all-zero label vector) are generated at roughly the same
   volume as any single scam label, because precision is the whole game: the
   Bible's Scenario D must stay Low.

Usage
-----
    .venv/bin/python -m ml.datagen --out data/train/corpus.jsonl --per-label 320
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from scoring.taxonomy import COUNTER_LABELS, LABELS, SCAM_LABELS  # noqa: E402

# --------------------------------------------------------------------------- slots
# Fictional institutions only - Bible §17 forbids real bank names in artifacts.
SLOTS: dict[str, list[str]] = {
    "bank": ["ApnaBank", "Apna Bank", "Metro Commercial Bank", "Metro Commercial",
             "National Apna Bank", "ApnaBank Limited", "Metro Bank"],
    "wallet": ["JazzCash", "Easypaisa", "Raast", "SadaPay", "NayaPay", "jazz cash",
               "easy paisa"],
    "telco": ["Jazz", "Telenor", "Ufone", "Zong", "PTA", "Jazz helpline"],
    "govt": ["FBR", "NADRA", "FIA", "Cyber Crime wing", "police station", "adalat",
             "court", "Anti Narcotics"],
    "utility": ["WAPDA", "LESCO", "K-Electric", "SNGPL", "gas department",
                "bijli department"],
    "courier": ["TCS", "Leopards", "DHL", "customs", "post office", "parcel service"],
    "techco": ["Microsoft", "Windows support", "mobile company", "app support",
               "technical department", "IT department"],
    "otp": ["OTP", "otp", "code", "kod", "verification code", "one time password",
            "one-time code", "verification kod", "sms code", "chhe digit ka code",
            "6 digit code", "pin code", "او ٹی پی", "ون ٹائم پاس ورڈ"],
    "cred": ["password", "pin", "PIN", "cvv", "CVV", "card number", "card ka number",
             "atm pin", "internet banking password", "CNIC number", "shanakhti card number",
             "پن کوڈ", "خفیہ کوڈ"],
    "amount": ["5000", "10 hazar", "50,000", "ek lakh", "25000", "dus hazar",
               "2 lakh", "15000 rupay", "chalees hazar", "پچاس ہزار",
               "دس ہزار روپے", "ایک لاکھ روپے"],
    "mins": ["5", "10", "2", "15", "30"],
    "dept": ["fraud department", "security department", "risk department",
             "verification department", "fraud prevention cell", "helpline",
             "فراڈ ڈیپارٹمنٹ"],
    "case": ["FIR 4471", "case number 8823", "reference number TG-9910",
             "complaint number 55231", "case ID 77120"],
    "name": ["Ahmed", "Bilal", "Sana", "Usman", "Ayesha", "Kamran", "Zainab"],
    "role": ["officer", "manager", "agent", "inspector", "representative",
             "senior officer", "team lead"],
    "link": ["bit.ly/apna-verify", "tinyurl.com/mcb-secure", "apnabank-verify.top",
             "metro-secure.xyz", "http://bit.ly/3xQz", "payment-confirm.online"],
    "app": ["AnyDesk", "TeamViewer", "QuickSupport", "screen share app", "remote app"],
    "job": ["data entry", "online typing", "part time work", "Amazon reviews",
            "product review", "packing job", "work from home"],
    "platform": ["WhatsApp", "Telegram", "whatsapp pe", "telegram pe", "IMO"],
    "country": ["Dubai", "Saudia", "London", "Canada", "Malaysia", "Turkey"],
    "relation": ["beta", "bhai", "cousin", "chacha ka beta", "bhatija", "nephew"],
}


# ------------------------------------------------------- Roman-Urdu orthographic drift
# Each key maps to interchangeable real-world spellings. Templates may reference a
# key as a {slot} to force variation at that position; on top of that, _drift()
# rewrites matching bare words probabilistically, so the model sees the same
# intent across many surface forms.
DRIFT: dict[str, list[str]] = {
    "paisay": ["paise", "pesay", "pese", "paisa", "pisay"],
    "batao": ["btao", "bata do", "bata dein", "batayen", "bta do", "batadein"],
    "karo": ["kro", "karein", "kar do", "kardo", "karlo"],
    "jaldi": ["jldi", "jaldee", "fori", "foran", "turant", "abhi"],
    "hai": ["hy", "he", "hai na", "h"],
    "nahi": ["nhi", "nahin", "ni", "nahe"],
    "aap": ["ap"],
    "account": ["akaunt", "acct", "khata", "a/c"],
    "transfer": ["trnsfr", "bhej", "send", "transfar"],
    "verify": ["verifiy", "verfiy", "tasdeeq", "confirm"],
    "kisi": ["ksi", "kisee"],
    "bhejo": ["bhej do", "bhejein", "bhj do", "send karo"],
    "sunao": ["suna do", "sunaein", "sunain", "bata do"],
    "block": ["blok", "band", "bnd"],
    "message": ["msg", "mesg", "sms", "text"],
}
_DRIFT_INDEX = {k: [k] + v for k, v in DRIFT.items()}

# Templates can use either a SLOTS key or a DRIFT key as a placeholder.
_FILL_SOURCES: dict[str, list[str]] = {**SLOTS, **_DRIFT_INDEX}


def _fill(template: str, rng: random.Random) -> str:
    out = template
    guard = 0
    while "{" in out and guard < 12:
        guard += 1
        for key, values in _FILL_SOURCES.items():
            token = "{" + key + "}"
            while token in out:
                out = out.replace(token, rng.choice(values), 1)
    return out


def _drift(text: str, rng: random.Random, rate: float = 0.55) -> str:
    words = text.split()
    out = []
    for w in words:
        low = w.lower().strip(".,!?")
        if low in _DRIFT_INDEX and rng.random() < rate:
            out.append(rng.choice(_DRIFT_INDEX[low]))
        else:
            out.append(w)
    return " ".join(out)


def _keyboard_noise(text: str, rng: random.Random, rate: float = 0.06) -> str:
    """Occasional dropped/doubled character - real chat messages are typo-ridden."""
    if rng.random() > rate or len(text) < 12:
        return text
    i = rng.randrange(len(text))
    if text[i].isalpha():
        return text[:i] + (text[i] * 2 if rng.random() < 0.5 else "") + text[i + 1:]
    return text


def _casing(text: str, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.10:
        return text.lower()
    if r < 0.14:
        return text.upper()
    return text


# --------------------------------------------------------------------------- templates
TEMPLATES: dict[str, list[str]] = {
    # ------------------------------------------------ Family A - impersonation
    "bank_impersonation": [
        "Assalam o alaikum, main {bank} ke {dept} se {role} {name} bol raha hoon",
        "This is {name} calling from {bank} {dept}",
        "{bank} se call kar raha hoon, aap ke {account} par masla hai",
        "Main {bank} ka {role} hoon, security alert aya hai aap ke {account} par",
        "Sir main {bank} head office se bol raha hoon",
        "{bank} customer care, hum ne suspicious activity detect ki hai",
        "میں {bank} کے فراڈ ڈیپارٹمنٹ سے بات کر رہا ہوں",
        "Hello, {bank} verification cell se rabta kiya ja raha hai",
        "I am from {bank}, our system flagged your {account}",
    ],
    "government_impersonation": [
        "Main {govt} se bol raha hoon, aap ke khilaf {case} darj hai",
        "This is {govt}, we have a case registered against your CNIC",
        "{govt} ki taraf se notice jari hua hai aap ke naam",
        "Main {govt} ka {role} hoon, aap ka naam investigation mein aya hai",
        "{govt} se {role} {name} bol raha hoon, {case} ke silsile mein",
        "میں {govt} سے بول رہا ہوں، آپ کے خلاف مقدمہ ہے",
        "Your CNIC has been used in illegal activity, {govt} inquiry chal rahi hai",
    ],
    "wallet_impersonation": [
        "Main {wallet} ke helpline se bol raha hoon",
        "{wallet} account verification ke liye call kiya hai",
        "This is {wallet} support, your wallet is under review",
        "{wallet} se {role} bol raha hoon, aap ka {account} block hone wala hai",
        "{wallet} agent hoon main, KYC update karna hai",
        "میں {wallet} کے دفتر سے بول رہا ہوں",
    ],
    "family_impersonation": [
        "Main aap ka {relation} hoon, naya number hai mera",
        "Ammi main {relation} bol raha hoon, mera phone kho gaya",
        "Hello beta, main tumhara chacha bol raha hoon {country} se",
        "Yaar main {name} hoon, purana number band ho gaya hai",
        "Main aap ka {relation} bol raha hoon, {country} mein phans gaya hoon",
        "میں آپ کا بیٹا بول رہا ہوں، میرا نمبر بدل گیا ہے",
    ],
    "telecom_impersonation": [
        "Main {telco} ke customer care se bol raha hoon",
        "{telco} se call hai, aap ki SIM band hone wali hai",
        "This is {telco} support, your SIM needs re-verification",
        "{telco} franchise se bol raha hoon, biometric verification pending hai",
        "{telco} ki taraf se aap ka number blacklist ho raha hai",
    ],
    "utility_impersonation": [
        "Main {utility} se bol raha hoon, aap ka connection kat jaye ga",
        "{utility} se call hai, bill pending hai aap ka",
        "This is {utility}, your meter reading shows illegal usage",
        "{utility} ka {role} hoon, disconnection notice jari hua hai",
        "{utility} se bol raha hoon, aaj hi bill clear karna hoga warna bijli band",
    ],
    "tech_support_impersonation": [
        "Main {techco} se bol raha hoon, aap ke computer mein virus hai",
        "This is {techco} technical support, your device is compromised",
        "{techco} se call kar raha hoon, aap ka app corrupt ho gaya hai",
        "Main {bank} app support se hoon, app update karwana hai",
        "{techco} ke engineer bol raha hoon, remote access chahiye hoga",
    ],
    "employer_recruiter_impersonation": [
        "Main HR department se bol raha hoon, aap ka CV shortlist hua hai",
        "We are hiring for {job}, main recruiter bol raha hoon",
        "{job} ke liye interview schedule karna hai, main company se hoon",
        "Main {name} HR manager hoon, aap ko job offer dena chahte hain",
        "Congratulations, aap ka selection ho gaya hai {job} ke liye",
    ],
    "courier_impersonation": [
        "Main {courier} se bol raha hoon, aap ka parcel ruka hua hai",
        "This is {courier}, your package is held at customs",
        "{courier} se call hai, delivery ke liye clearance chahiye",
        "Aap ka parcel {courier} office mein hai, customs duty pending hai",
    ],
    "authority_claim": [
        "Mera employee ID {case} hai, aap note kar lein",
        "Main senior {role} hoon, meri authority se ye kaam ho sakta hai",
        "My badge number is {case}, you can verify later",
        "Main authorized {role} hoon is department ka",
        "{case} ke tehat main aap se baat kar raha hoon",
    ],

    # ------------------------------------------ Family B - financial & credential
    "otp_harvesting": [
        "Aap ko jo {otp} aya hai wo mujhe {batao}",
        "Please read me the {otp} you just received",
        "{otp} {sunao} jaldi, verification complete karna hai",
        "Jo {message} aya hai us mein {otp} likha hai, wo bata dein",
        "Sir {otp} share {karo} warna process cancel ho jaye ga",
        "آپ کو جو کوڈ آیا ہے وہ مجھے بتائیں",
        "I need the {otp} to verify your identity, tell me now",
        "Screen par jo {otp} show ho raha hai wo mujhe likh kar bhejo",
        "Us {message} ka number {batao} jo abhi aya",
        "{otp} confirm {karo} phir main aage barhta hoon",
        "Wo chhe ainkon wala number jo aya hai wo {sunao}",
    ],
    "credential_request": [
        "Aap ka {cred} {batao} verification ke liye",
        "Tell me your {cred} so I can access the system",
        "{cred} share {karo} warna {account} block ho jaye ga",
        "Mujhe aap ka {cred} chahiye confirmation ke liye",
        "Internet banking ka {cred} bata dein please",
        "اپنا پن کوڈ بتائیں تاکہ ہم تصدیق کر سکیں",
        "Full {cred} likh kar bhej dein, security check hai",
        "Apna {cred} aur date of birth confirm {karo}",
    ],
    "payment_request_disguised_as_receipt": [
        "Sorry ghalti se aap ke {account} mein {amount} chale gaye, wapas {bhejo}",
        "I accidentally sent {amount} to you, please return it",
        "Bhai mistake ho gayi, {amount} transfer ho gaye aap ko, please wapas {karo}",
        "Ye receipt dekhein, {amount} aap ko bhej diye, ab wapas {bhejo}",
        "Screenshot bhej raha hoon, {amount} aa gaye hain, refund {karo}",
        "غلطی سے آپ کو پیسے چلے گئے ہیں، واپس بھیج دیں",
    ],
    "account_number_request": [
        "Aap ka {account} number {batao}, main {amount} bhej deta hoon",
        "Send me your IBAN so I can transfer the prize money",
        "{account} details {batao}, refund process karna hai",
        "Apna {wallet} number {batao} paise bhejne ke liye",
        "Bank {account} number aur title bata dein",
    ],
    "upfront_fee_demand": [
        "Registration ke liye {amount} deposit {karo} phir job confirm",
        "You need to pay {amount} processing fee first, it is refundable",
        "{amount} security deposit {bhejo}, baad mein wapas mil jayen ge",
        "Pehle {amount} ki fee jama {karo} phir parcel release hoga",
        "Training kit ke liye {amount} bhejna hoga, refundable hai",
        "Customs duty {amount} pay {karo} to release your parcel",
    ],
    "payment_redirection": [
        "Is baar paise dosray {account} mein {bhejo}, purana band hai",
        "Please send the payment to this new account instead",
        "Naya {wallet} number note {karo}, ab isi par {transfer} {karo}",
        "Company ka account change ho gaya hai, is number par {bhejo}",
        "Direct mere personal {account} mein {bhejo}, company account slow hai",
    ],
    "suspicious_link": [
        "Is link par click {karo} aur details bharein {link}",
        "Verify your account here: {link}",
        "{link} par jaa kar apni information update {karo}",
        "Payment ke liye ye link use {karo} {link}",
        "Form fill {karo} is link se {link} warna {account} band",
    ],
    "remittance_request": [
        "Jaldi {amount} {transfer} {karo}, main {country} mein phans gaya hoon",
        "Please wire {amount} urgently, it is an emergency",
        "{amount} bhej dein {jaldi}, hospital mein hoon",
        "Western Union se {amount} bhejo abhi, bohat zaroori hai",
        "{country} mein visa ke liye {amount} chahiye {jaldi}",
    ],
    "investment_pitch": [
        "Is scheme mein {amount} lagao, double return guaranteed",
        "Guaranteed 40% monthly profit, crypto trading group join {karo}",
        "Meri company mein invest {karo}, koi risk {nahi} hai",
        "Trading signals group hai, {amount} se start {karo} aur roz profit",
        "Bitcoin doubling scheme, {amount} do aur {amount} lo",
        "Forex mein paise lagao, guaranteed profit hai bilkul safe",
    ],
    "prize_lottery_claim": [
        "Congratulations, aap ne {amount} ka inaam jeeta hai",
        "You have won {amount} in our lucky draw",
        "{telco} lucky draw mein aap ka number nikla hai, {amount} ka prize",
        "Aap ki SIM par {amount} ka bumper prize aya hai",
        "مبارک ہو، آپ نے انعام جیتا ہے",
    ],

    # -------------------------------------- Family C - manipulation & behaviour
    "threat_intimidation": [
        "Agar ab {nahi} kiya to aap ka {account} permanently {block} ho jaye ga",
        "Warrant jari ho jaye ga aap ke naam, arrest ho sakti hai",
        "Legal action le liya jaye ga, court mein case chala jaye ga",
        "Aap ka CNIC blacklist ho jaye ga aur jurmana bhi hoga",
        "Police aap ke ghar aa jaye gi agar cooperate {nahi} kiya",
        "آپ کا اکاؤنٹ بلاک ہو جائے گا اور قانونی کارروائی ہوگی",
    ],
    "isolation_pressure": [
        "{kisi} ko {batao} mat, branch bhi mat jao",
        "Do not discuss this with your family, it is confidential",
        "Ghar walon ko {batao} ki zarurat {nahi}, main khud handle kar raha hoon",
        "Branch call {karo} mat, wo log aur confuse karen ge",
        "Apne bete ko involve {nahi} {karo}, ye simple process hai",
    ],
    "verification_avoidance": [
        "Helpline par call {karo} mat, wo busy rehti hai main khud kar deta hoon",
        "You cannot call back, this is an outgoing-only secure line",
        "Official number par call karne ki zarurat {nahi} hai",
        "Main aap ko call back {nahi} kar sakta, abhi hi complete karna hoga",
        "App se {verify} {nahi} hoga, sirf main kar sakta hoon",
    ],
    "escalation_after_hesitation": [
        "Aap meri baat {nahi} sun rahe, main apne senior ko de raha hoon",
        "You are wasting my time, I have other customers waiting",
        "Main {role} ko line par la raha hoon, wo aap ko samjhayen ge",
        "Aap ki wajah se mera record kharab ho raha hai, please cooperate",
        "Itni si baat samajh {nahi} aa rahi? Main gussa ho raha hoon",
    ],
    "urgency_pressure": [
        "Sirf {mins} minute hain, {jaldi} {karo}",
        "This must be done within {mins} minutes or the transaction fails",
        "Aaj hi karna hoga, kal deadline khatam",
        "System {mins} minute mein timeout ho jaye ga, {jaldi}",
        "{jaldi} {karo} time nikal raha hai",
        "صرف دس منٹ باقی ہیں، جلدی کریں",
    ],
    "secrecy_request": [
        "{kisi} ko {nahi} {batao}, ye confidential process hai",
        "Keep this between us, do not tell anyone",
        "Ye baat sirf aap aur mere darmiyan rahe",
        "{kisi} se discuss {nahi} karna, security policy hai",
        "کسی کو نہ بتائیں، یہ راز ہے",
    ],
    "emotional_exploitation": [
        "Meri maa hospital mein hai, please madad {karo}",
        "I have nobody else to turn to, you are my only hope",
        "Main bohat pareshan hoon, aap hi meri madad kar sakte hain",
        "Tum ne kaha tha tum mera khayal rakho ge, ab pichhe hat rahe ho",
        "Bachay bhookay hain, {jaldi} kuch {karo}",
    ],
    "rapid_intimacy": [
        "Do din mein hi lagta hai main tum se pyar karne laga hoon",
        "I have never felt this connected to anyone so quickly",
        "Tum meri zindagi ki sab se acchi baat ho, shaadi karen ge hum",
        "Main tumhein apni jaan samajhta hoon, itni jaldi kabhi {nahi} hua",
        "Tum se baat kar ke lagta hai barson ka rishta hai",
    ],
    "false_credibility_props": [
        "Mera employee card ka photo bhej raha hoon dekh lein",
        "Here is my official ID and the {case} document",
        "Screenshot dekhein, ye {bank} ka official portal hai",
        "Meri company ki registration certificate bhej deta hoon",
        "Ye {case} number official record mein hai, check kar lein",
    ],
    "trust_acceleration": [
        "Main aap ko apna bhai samajhta hoon, is liye bata raha hoon",
        "You can trust me completely, I am here to protect you",
        "Hum purane customers ka khaas khayal rakhte hain",
        "Main aap ki jagah hota to bhi yehi karta, mera aitbaar {karo}",
    ],
    "platform_migration": [
        "{platform} par aa jao, wahan baat karna easy hai",
        "Let us continue this on {platform}",
        "Yahan message delete ho jate hain, {platform} par message {karo}",
        "Mera {platform} number save {karo}, wahan detail bhejta hoon",
    ],
    "boundary_probing": [
        "Pehle sirf ek chhota sa test transfer {karo}, 100 rupay",
        "Just confirm the last four digits for now, nothing else",
        "Sirf apna naam aur city {batao}, baaki baad mein",
        "Chalo pehle {amount} se shuru karte hain, phir barhayen ge",
    ],
    "persistence_repetition": [
        "Main phir puchh raha hoon, {otp} {batao}",
        "I asked you already, please give me the code",
        "Aap ne abhi tak {nahi} bataya, dobara puchh raha hoon",
        "Teesri baar keh raha hoon, {cred} share {karo}",
    ],
    "unsolicited_contact_origin": [
        "Assalam o alaikum, aap ka number mujhe kahin se mila tha",
        "Hi, I got your number from a mutual friend",
        "Sorry wrong number tha lekin baat karne ka mann hua",
        "Aap ka number randomly aa gaya, kya baat kar sakte hain",
    ],

    # ------------------------------------- Family D - context-safe counter-signals
    "legitimate_otp_context": [
        "Main ne khud login kiya hai is liye {otp} aya hai",
        "I just requested this code myself for my own login",
        "Maine abhi payment initiate ki thi, us ka {otp} hai ye",
        "Ye {otp} mera hi hai, main app par sign in kar raha tha",
        "Do not share this code with anyone. {bank} will never ask for it.",
        "Your {otp} is 449213. Never share it with anyone including {bank} staff.",
    ],
    "known_contact_context": [
        "Ye mera purana dost hai, dus saal se jaanta hoon",
        "This is my brother, I have his number saved",
        "Mummy ka number hai, roz baat hoti hai",
        "Ye meri behen hai, contact list mein saved hai",
    ],
    "verifiable_identity": [
        "Aap {bank} ke official helpline par call kar ke confirm kar lein",
        "Please hang up and call the number printed on your card",
        "Main aap ko wait karwa deta hoon, aap branch se {verify} kar lein",
        "Aap app ke andar se ticket check kar lein, main intezar karta hoon",
    ],
    "platform_official_channel": [
        "Ye message {bank} ke official short code se aya hai",
        "Sender ID {bank} verified hai, short code 8080",
        "Official {wallet} short code se notification hai ye",
    ],
}

# --------------------------------------------------------- Urdu-script templates
# Native-script counterparts of the template bank - the way these lines are
# actually spoken and texted on Pakistani scam calls. Slots stay shared: real
# Urdu conversations mix scripts freely ("مجھے ApnaBank سے کال آئی تھی"), which
# is exactly the code-switching the trained tier has to survive. Template ids
# carry an "urdu_" prefix, so the template-disjoint split treats the script bank
# as its own group and validation Urdu is phrasing the model never saw - in
# either script.
URDU_TEMPLATES: dict[str, list[str]] = {
    # ------------------------------------------------ Family A - impersonation
    "bank_impersonation": [
        "میں {bank} کی فریڈ ڈیپارٹمنٹ سے بول رہا ہوں",
        "یہاں {bank} ہیڈ آفس سے کال آئی ہے",
        "السلام علیکم، میں {bank} کا {role} {name} بول رہا ہوں",
        "ہم {bank} سے بات کر رہے ہیں، آپ کے اکاؤنٹ پر مشکوک سرگرمی ہوئی ہے",
    ],
    "government_impersonation": [
        "میں {govt} سے بول رہا ہوں، آپ کے خلاف مقدمہ درج ہے",
        "یہاں {govt} کی طرف سے کال ہے، آپ کا شناختی کارڈ ایک مقدمے میں پایا گیا ہے",
        "میں {govt} کا {role} ہوں، آپ کا نام انکوائری میں آیا ہے",
        "{govt} سے آپ کے نام کا نوٹس جاری ہوا ہے",
    ],
    "wallet_impersonation": [
        "میں {wallet} کے ہیلپ لائن سے بول رہا ہوں",
        "یہ {wallet} سپورٹ ہے، آپ کا اکاؤنٹ ریویو میں ہے",
        "{wallet} سے {role} بول رہا ہوں، آپ کی KYC اپڈیٹ کروانی ہے",
        "میں {wallet} کا ایجنٹ ہوں، آپ کی تصدیق باقی ہے",
    ],
    "family_impersonation": [
        "میں آپ کا بیٹا بول رہا ہوں، میرا نمبر بدل گیا ہے",
        "امی، میں بول رہا ہوں، میرا فون کہیں گم ہو گیا ہے",
        "بیٹا، میں تمہارا چچا بول رہا ہوں، {country} سے",
        "میں آپ کا {relation} ہوں، {country} میں پھنس گیا ہوں",
    ],
    "telecom_impersonation": [
        "میں {telco} کسٹمر کیئر سے بول رہا ہوں",
        "{telco} سے کال ہے، آپ کی سِم بند ہونے والی ہے",
        "یہاں {telco} فرنچائز سے بات ہو رہی ہے، بایومیٹرک تصدیق باقی ہے",
        "{telco} کی طرف سے آپ کا نمبر بلیک لسٹ ہو رہا ہے",
    ],
    "utility_impersonation": [
        "میں {utility} سے بول رہا ہوں، آپ کا کنکشن کٹ جائے گا",
        "{utility} سے کال ہے، آپ کا بل پینڈنگ ہے",
        "میں {utility} کا {role} ہوں، منقطعی کا نوٹس جاری ہو گیا ہے",
        "آج ہی بل کلیئر کریں ورنہ رات کو بجلی بند ہو جائے گی",
    ],
    "tech_support_impersonation": [
        "میں {techco} سے بول رہا ہوں، آپ کے کمپیوٹر میں وائرس ہے",
        "یہاں {techco} ٹیکنیکل سپورٹ سے بات ہو رہی ہے، آپ کا ڈیوائس خطرے میں ہے",
        "میں {bank} ایپ سپورٹ سے ہوں، ایپ اپڈیٹ کروانی ہے",
        "{techco} کا انجینئر بول رہا ہوں، ریموٹ ایکسیس چاہیے ہوگا",
    ],
    "employer_recruiter_impersonation": [
        "میں ایچ آر ڈیپارٹمنٹ سے بول رہا ہوں، آپ کا سی وی شارٹ لسٹ ہو گیا ہے",
        "ہم {job} کے لیے بھرتی کر رہے ہیں، انٹرویو فکس کرنا ہے",
        "میں {name} ایچ آر مینیجر ہوں، آپ کو نوکری کی پیشکش دینا چاہتے ہیں",
        "مبارک ہو، آپ کا سلیکشن ہو گیا ہے {job} کے لیے",
    ],
    "courier_impersonation": [
        "میں {courier} سے بول رہا ہوں، آپ کا پارسل رکا ہوا ہے",
        "یہاں {courier} سے کال ہے، آپ کا پیکج کسٹم میں پھنسا ہے",
        "آپ کا پارسل {courier} آفس میں ہے، ڈیوٹی پینڈنگ ہے",
        "ڈیلیوری کے لیے کلیرنس فیس جمع کروانی ہوگی",
    ],
    "authority_claim": [
        "میرا ایمپلائی آئی ڈی {case} ہے، نوٹ کر لیں",
        "میں سینئر {role} ہوں، میری اجازت سے یہ کام ہو سکتا ہے",
        "میں اس ڈیپارٹمنٹ کا مجاز {role} ہوں",
        "{case} کے تحت میں آپ سے بات کر رہا ہوں",
    ],

    # ------------------------------------------ Family B - financial & credential
    "otp_harvesting": [
        "آپ کو جو او ٹی پی آیا ہے وہ فوراً بٹا دیں",
        "او ٹی پی کا کوڈ بتائیں تاکہ تصدیق ہو سکے",
        "جو {otp} آیا ہے وہ مجھے سنائیں، جلدی کریں",
        "اسکرین پر جو کوڈ دکھ رہا ہے وہ لکھ کر بھیج دیں",
    ],
    "credential_request": [
        "اپنا {cred} بتا دیں، تصدیق کے لیے ضروری ہے",
        "انٹرنیٹ بینکنگ کا پاس ورڈ سنائیں",
        "مجھے آپ کا {cred} چاہیے، کنفرمیشن کرنی ہے",
        "{cred} شیئر کریں ورنہ اکاؤنٹ بلاک ہو جائے گا",
    ],
    "payment_request_disguised_as_receipt": [
        "معاف کیجیے، غلطی سے {amount} آپ کے اکاؤنٹ میں چلے گئے، واپس بھیج دیں",
        "بھائی، غلطی ہو گئی، {amount} آپ کو ٹرانسفر ہو گئے ہیں، واپس کر دیں",
        "یہ رسیٹ دیکھیں، {amount} بھیج دیے ہیں، اب واپس کریں",
        "اسکرین شاٹ بھیج رہا ہوں، {amount} آ گئے ہیں، ریفنڈ کر دیں",
    ],
    "account_number_request": [
        "اپنا اکاؤنٹ نمبر بتائیں، میں {amount} بھیج دیتا ہوں",
        "اپنا {wallet} نمبر بتا دیں، پیسے بھیجنے ہیں",
        "بینک اکاؤنٹ نمبر اور ٹائٹل سنائیں",
        "انعام کی رقم بھیجنے کے لیے اپنا آئی بی اے این بتا دیں",
    ],
    "upfront_fee_demand": [
        "رجسٹریشن کے لیے {amount} جمع کروائیں، پھر نوکری کنفرم ہوگی",
        "پہلے {amount} پراسیسنگ فیس ادا کریں، یہ واپس مل جائے گی",
        "سیکورٹی ڈپازٹ {amount} بھیج دیں، بعد میں واپس مل جائے گا",
        "کسٹم ڈیوٹی {amount} ادا کریں تو آپ کا پارسل رہا ہوگا",
        "ٹریننگ کٹ کے لیے {amount} بھیجنا ہوگا، ریفنڈ ایبل ہے",
    ],
    "payment_redirection": [
        "اس بار پیسے دوسرے اکاؤنٹ میں بھیجیں، پرانا بند ہے",
        "نئے {wallet} نمبر پر نوٹ کر لیں، اب اسی پر بھیجیں",
        "کمپنی کا اکاؤنٹ بدل گیا ہے، اس نمبر پر بھیج دیں",
        "براہ راست میرے ذاتی اکاؤنٹ میں بھیج دیں، کمپنی والا سست ہے",
    ],
    "suspicious_link": [
        "اس لنک پر کلک کریں اور تفصیل بھر دیں {link}",
        "{link} پر جا کر اپنی معلومات اپڈیٹ کریں",
        "فارم اسی لنک سے بھریں {link} ورنہ اکاؤنٹ بند",
        "ادائیگی کے لیے یہ لنک استعمال کریں {link}",
    ],
    "remittance_request": [
        "جلدی {amount} بھیج دیں، میں {country} میں پھنسا ہوں",
        "{amount} فوراً بھیجیں، ہسپتال میں ہوں، ایمرجنسی ہے",
        "ویسٹرن یونین سے {amount} بھیج دیں ابھی، بہت ضروری ہے",
        "{country} میں ویزے کے لیے {amount} چاہیے، جلدی کریں",
    ],
    "investment_pitch": [
        "اس اسکیم میں {amount} لگا دیں، ڈبل ریٹرن گارنٹیڈ ہے",
        "میری کمپنی میں انویسٹ کریں، کوئی رسک نہیں",
        "ٹریڈنگ سگنلز کا گروپ ہے، {amount} سے شروع کریں اور روز منافع لیں",
        "بٹ کوائن ڈبل ہونے والی اسکیم ہے، {amount} دیں اور ڈبل وصول کریں",
        "فاریکس میں پیسے لگائیں، منافع گارنٹیڈ ہے، بالکل محفوظ",
    ],
    "prize_lottery_claim": [
        "مبارک ہو، آپ نے {amount} کا انعام جیتا ہے",
        "{telco} لکی ڈرا میں آپ کا نمبر نکلا ہے، {amount} کا پرائز",
        "آپ کی سِم پر {amount} کا بمپر پرائز آیا ہے",
        "آپ ہمارے لکی ڈرا میں جیت گئے ہیں، رقم لینے کے لیے فارم بھریں",
    ],

    # -------------------------------------- Family C - manipulation & behaviour
    "threat_intimidation": [
        "اگر اب نہ کیا تو آپ کا اکاؤنٹ ہمیشہ کے لیے بلاک ہو جائے گا",
        "آپ کے نام وارنٹ جاری ہو جائے گا، گرفتاری بھی ہو سکتی ہے",
        "قانونی کارروائی ہوگی، عدالت میں کیس چلے گا",
        "پولیس آپ کے گھر آ جائے گی اگر تعاون نہ کیا",
        "آپ کا شناختی کارڈ بلیک لسٹ ہو جائے گا اور جرمانہ بھی لگے گا",
    ],
    "isolation_pressure": [
        "کسی کو بتائیں نہیں، برانچ بھی مت جائیں",
        "گھر والوں کو بتانے کی ضرورت نہیں، میں خود نمٹ رہا ہوں",
        "برانچ کو کال نہ کریں، وہ لوگ اور الجھیں گے",
        "اپنے بیٹے کو شامل نہ کریں، یہ سادہ سا عمل ہے",
    ],
    "verification_avoidance": [
        "ہیلپ لائن پر کال نہ کریں، وہ مصروف رہتی ہے، میں خود کر دیتا ہوں",
        "آپ کال بیک نہیں کر سکتے، یہ صرف باہر جانے والی سکیورٹی لائن ہے",
        "آفیشل نمبر پر کال کرنے کی ضرورت نہیں",
        "میں آپ کو واپس کال نہیں کر سکتا، ابھی مکمل کرنا ہوگا",
        "ایپ سے تصدیق نہیں ہوگی، صرف میں خود کر سکتا ہوں",
    ],
    "escalation_after_hesitation": [
        "آپ میری بات نہیں سن رہے، میں اپنے سینئر کو دے رہا ہوں",
        "آپ میرا وقت ضائع کر رہے ہیں، دوسرے کسٹمر بھی انتظار میں ہیں",
        "میں {role} کو لائن پر لا رہا ہوں، وہ آپ کو سمجھائیں گے",
        "اتنی سی بات سمجھ نہیں آ رہی؟ مجھے غصہ آ رہا ہے",
        "آپ کی وجہ سے میرا ریکارڈ خراب ہو رہا ہے، تعاون کیجیے",
    ],
    "urgency_pressure": [
        "صرف {mins} منٹ باقی ہیں، فوراً کریں",
        "آج ہی کرنا ہوگا، کل ڈیڈلائن ختم ہو جائے گی",
        "سسٹم {mins} منٹ میں ٹائم آؤٹ ہو جائے گا، جلدی کریں",
        "وقت نکل رہا ہے، ابھی کریں",
    ],
    "secrecy_request": [
        "کسی کو نہ بتائیں، یہ خفیہ بات ہے",
        "یہ بات صرف ہم دونوں کے درمیان رہے",
        "کسی سے بحث نہ کریں، یہ سیکیورٹی پالیسی ہے",
        "کسی کو خبر نہ ہو، راز رکھیں",
    ],
    "emotional_exploitation": [
        "میری ماں ہسپتال میں داخل ہے، اللہ کے لیے مدد کریں",
        "میرے پاس کوئی اور سہارا نہیں، آپ ہی میری آخری امید ہیں",
        "میں بہت پریشان حال ہوں، صرف آپ ہی میری مدد کر سکتے ہیں",
        "بچے بھوکے سو رہے ہیں، جلدی کچھ کیجیے",
    ],
    "rapid_intimacy": [
        "دو دن میں ہی لگتا ہے میں تم سے پیار کرنے لگا ہوں",
        "میں تمہیں اپنی جان سمجھتا ہوں، اتنی جلدی پہلے کبھی نہیں ہوا",
        "تم میری زندگی کی سب سے اچھی بات ہو، ہم شادی کریں گے",
        "تم سے بات کر کے لگتا ہے برسوں پرانا رشتہ ہے",
    ],
    "false_credibility_props": [
        "میرے ایمپلائی کارڈ کی تصویر بھیج رہا ہوں، دیکھ لیں",
        "یہ میری سرکاری آئی ڈی اور {case} کی دستاویز ہے",
        "اسکرین شاٹ دیکھیں، یہ {bank} کا آفیشل پورٹل ہے",
        "میری کمپنی کا رجسٹریشن سرٹیفکیٹ بھیج دیتا ہوں",
    ],
    "trust_acceleration": [
        "میں آپ کو اپنا بھائی سمجھتا ہوں، اسی لیے بتا رہا ہوں",
        "مجھ پر پورا بھروسہ کریں، میں آپ کی حفاظت کے لیے ہی تو ہوں",
        "ہم پرانے گاہکوں کا خاص خیال رکھتے ہیں",
        "میں آپ کی جگہ ہوتا تو یہی کرتا، مجھ پر اعتماد کیجیے",
    ],
    "platform_migration": [
        "{platform} پر آ جائیں، وہاں بات کرنا آسان ہے",
        "یہاں پیغام ڈیلیٹ ہو جاتے ہیں، {platform} پر پیغام کریں",
        "میرا {platform} نمبر محفوظ کر لیں، وہاں تفصیل بھیجتا ہوں",
        "آئیں {platform} پر، وہاں آرام سے بات ہو جائے گی",
    ],
    "boundary_probing": [
        "پہلے صرف ایک چھوٹا سا ٹیسٹ ٹرانسفر کر دیں، سو روپے کا",
        "ابھی بس آخری چار ہندسے بتا دیں، کچھ اور نہیں",
        "پہلے صرف اپنا نام اور شہر بتائیں، باقی بعد میں",
        "چلیں پہلے {amount} سے شروع کرتے ہیں، پھر بڑھاتے ہیں",
    ],
    "persistence_repetition": [
        "میں دوبارہ پوچھ رہا ہوں، کوڈ بتا دیں",
        "میں نے پہلے ہی کہہ دیا تھا، او ٹی پی سنائیں",
        "آپ نے ابھی تک نہیں بتایا، پھر پوچھ رہا ہوں",
        "تیسری بار کہہ رہا ہوں، اپنا {cred} شیئر کریں",
    ],
    "unsolicited_contact_origin": [
        "السلام علیکم، آپ کا نمبر مجھے کہیں سے مل گیا تھا",
        "آپ کا نمبر رینڈم آ گیا، کیا بات کر سکتے ہیں؟",
        "معاف کیجیے، غلط نمبر لگا تھا لیکن بات کرنے کا دل ہوا",
        "ایک مشترکہ دوست نے آپ کا نمبر دیا تھا",
    ],

    # ------------------------------------- Family D - context-safe counter-signals
    "legitimate_otp_context": [
        "میں نے خود لاگ ان کیا تھا، اسی لیے کوڈ آیا ہے",
        "میں نے خود ادائیگی شروع کی تھی، یہ اسی کا او ٹی پی ہے",
        "یہ کوڈ میرا ہی ہے، میں ایپ میں سائن ان کر رہا تھا",
        "یہ کوڈ کسی کو نہ بتائیں، {bank} کبھی نہیں مانگتا",
    ],
    "known_contact_context": [
        "یہ میرا پرانا دوست ہے، دس سال سے جانتا ہوں",
        "یہ میرا بھائی ہے، نمبر میرے فون میں محفوظ ہے",
        "امی کا نمبر ہے، روز بات ہوتی ہے",
        "یہ میری بہن ہے، کانٹیکٹ لسٹ میں محفوظ ہے",
    ],
    "verifiable_identity": [
        "آپ {bank} کی آفیشل ہیلپ لائن پر کال کر کے تصدیق کر لیں",
        "کال بند کیجیے اور اپنے کارڈ کے پیچھے لکھے نمبر پر کال کریں",
        "آپ برانچ سے تصدیق کر لیں، میں انتظار کرتا ہوں",
        "آپ ایپ کے اندر سے ٹکٹ چیک کر لیں، میں منتظر ہوں",
    ],
    "platform_official_channel": [
        "یہ پیغام {bank} کے آفیشل شارٹ کوڈ سے آیا ہے",
        "سینڈر آئی ڈی {bank} تصدیق شدہ ہے، شارٹ کوڈ 8080",
        "یہ آفیشل {wallet} شارٹ کوڈ سے آنے والا نوٹیفکیشن ہے",
    ],
}

# ------------------------------------------------------------------------ benign pool
BENIGN: list[str] = [
    "Assalam o alaikum, kaise hain aap? Ghar par sab theek?",
    "Kal shaam milte hain chai peene, 6 baje?",
    "Beta khana kha liya? Time par so jao",
    "Match dekha kal ka? Kya finish tha yaar",
    "Meeting 3 baje hai, conference room mein",
    "Salary aa gayi hai account mein, alhamdulillah",
    "Bhai wo book wapas kar dena jab time mile",
    "Doctor ne appointment Tuesday 4pm di hai, confirm kar dein",
    "Your order has been shipped and will arrive Thursday",
    "Happy birthday! Allah aap ko lambi umar de",
    "Kya tum ne assignment submit kar di?",
    "Petrol price phir barh gaya hai yaar",
    "Ammi ki tabiyat behtar hai ab, shukriya poochne ka",
    "Weekend par Murree jane ka plan hai, chalo ge?",
    "Main office pohanch gaya hoon, tum kahan ho?",
    "Bijli chali gayi hai, generator on kar do",
    "Kal jumma hai, jaldi band ho jaye ga office",
    "Wo file email kar di hai, check kar lena",
    "Beta result kab aa raha hai?",
    "Chalo phir kal baat karte hain, good night",
    "Mujhe lagta hai humein investment plan family ke sath discuss karna chahiye",
    "Papa ne kaha hai property ke paise bank mein rakhte hain",
    "Maine OLX par mobile bech diya, buyer ne cash diya tha",
    "Rent ki payment kar di hai landlord ko",
    "Tumhara birthday gift le liya hai, surprise hai",
    "Sabzi le aana wapsi par, tamatar aur pyaz",
    "Exam ki tayari kaisi chal rahi hai?",
    "Traffic bohat hai, thora late ho jaunga",
    "Thanks for the help yesterday, really appreciated it",
    "Cricket practice subah 7 baje hai, late na hona",
    "Maine apna naya laptop le liya, kaam tez ho gaya",
    "Dinner banaya hai, aa jao jaldi",
    "Kal ka lecture miss ho gaya, notes bhej do",
    "Eid ki shopping karni hai, chalo saath",
    "Loan ki installment kal due hai, bank jaana hai",
    "Insurance policy renew karwa li hai",
    "Beta ye month ki fees jama kar dena school mein",
    "Maine apni bike service karwa li",
    "Aaj mausam bohat acha hai, walk pe jayen?",
    "Wo restaurant acha tha, phir jayen ge",
]

# Urdu-script everyday messages. Benign volume has to exist in BOTH scripts:
# trained on Urdu scams + Roman benigns only, the model would learn "Urdu
# script == scam" and false-fire on perfectly ordinary Urdu chat (the precision
# failure mode Scenario D exists to guard against).
URDU_BENIGN: list[str] = [
    "السلام علیکم، کیسے ہیں آپ؟ گھر میں سب خیریت ہے؟",
    "کل شام چائے پر ملیں گے، چھ بجے؟",
    "بیٹا کھانا کھا لیا؟ وقت پر سو جائیں",
    "کل کا میچ دیکھا؟ کیا فنش تھا یار",
    "میٹنگ تین بجے ہے، کانفرنس روم میں",
    "تنخواہ اکاؤنٹ میں آ گئی ہے، الحمدللہ",
    "بھائی وہ کتاب واپس کر دینا جب وقت ملے",
    "ڈاکٹر نے منگل کو چار بجے اپائنٹمنٹ دی ہے، تصدیق کر لیں",
    "آپ کا آرڈر روانہ کر دیا گیا ہے، جمعرات کو پہنچ جائے گا",
    "سالگرہ مبارک! اللہ آپ کو لمبی عمر دے",
    "کیا تم نے اسائنمنٹ جمع کر دی؟",
    "پیٹرول کی قیمت پھر بڑھ گئی ہے یار",
    "امی کی طبیعت بہتر ہے اب، پوچھنے کا شکریہ",
    "ویک اینڈ پر مری جانے کا پلان ہے، چلو گے؟",
    "میں دفتر پہنچ گیا ہوں، تم کہاں ہو؟",
    "بجلی چلی گئی ہے، جنریٹر آن کر دیں",
    "وہ فائل ای میل کر دی ہے، دیکھ لینا",
    "بیٹا رزلٹ کب آ رہا ہے؟",
    "چلو پھر کل بات کریں گے، شب بخیر",
    "سبزی لے آنا واپسی پر، ٹماٹر اور پیاز",
    "امتحان کی تیاری کیسی چل رہی ہے؟",
    "ٹریفک بہت ہے، تھوڑا لیٹ ہو جاؤں گا",
    "کل کا لیکچر رہ گیا، نوٹس بھیج دو",
    "عید کی شاپنگ کرنی ہے، ساتھ چلیں گے؟",
    "کرایہ کی ادائیگی مالک کو کر دی ہے",
    "گھر آ رہا ہوں، رات کو کیا بنانا ہے کھانے میں؟",
]


def _has_urdu(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text)


def _compose(a: str, b: str, rng: random.Random) -> str:
    # Urdu clauses get Urdu joiners (، اور ۔) so composed samples read natural;
    # Roman clauses keep the Roman-Urdu joiner pool.
    if _has_urdu(a):
        joiner = rng.choice(["، ", "۔ ", " اور ", " - ", "، پھر ", "۔ اب "])
    else:
        joiner = rng.choice([", ", ". ", " aur ", " - ", ", phir ", ". Ab "])
    return a.rstrip(".") + joiner + (b[0].lower() + b[1:] if rng.random() < 0.5 else b)


def build_corpus(per_label: int, seed: int = 1337, compose_ratio: float = 0.35,
                 urdu_ratio: float = 0.35) -> list[dict]:
    rng = random.Random(seed)
    labels = sorted(SCAM_LABELS | COUNTER_LABELS)
    missing = [l for l in labels if l not in TEMPLATES or l not in URDU_TEMPLATES]
    if missing:
        raise SystemExit(f"templates missing for labels: {missing}")

    rows: list[dict] = []

    def render(label: str) -> tuple[str, str]:
        """Render one sample; also return the template id it came from.

        The template id is what makes an honest evaluation possible: train.py
        splits on it so validation only contains phrasings the model never saw.
        Urdu-bank renders carry an "urdu_<label>#<idx>" id, so the script bank
        is its own split group - held-out Urdu phrasings are unseen in either
        script, keeping the template-disjoint split honest.
        """
        if rng.random() < urdu_ratio:
            idx = rng.randrange(len(URDU_TEMPLATES[label]))
            s = _fill(URDU_TEMPLATES[label][idx], rng)
            tid = f"urdu_{label}#{idx}"
        else:
            idx = rng.randrange(len(TEMPLATES[label]))
            s = _fill(TEMPLATES[label][idx], rng)
            tid = f"{label}#{idx}"
        # _drift only knows Roman spellings, so it no-ops on Urdu script (the
        # embedded Latin slot values are not drift words); keyboard noise
        # applies to both scripts, which is exactly how real typos happen.
        s = _drift(s, rng)
        s = _keyboard_noise(s, rng)
        return _casing(s, rng), tid

    # single-label samples
    for label in labels:
        for _ in range(per_label):
            text, tid = render(label)
            rows.append({"text": text, "labels": [label], "template_ids": [tid]})

    # composed multi-label samples - real scam lines bundle signals
    n_composed = int(len(labels) * per_label * compose_ratio)
    positives = sorted(SCAM_LABELS)
    for _ in range(n_composed):
        a, b = rng.sample(positives, 2)
        # composing a counter-signal with a scam signal would be contradictory,
        # so composition stays inside the positive families.
        ta, tid_a = render(a)
        tb, tid_b = render(b)
        rows.append({
            "text": _compose(ta, tb, rng),
            "labels": sorted({a, b}),
            "template_ids": sorted({tid_a, tid_b}),
        })

    # benign - volume matched so precision holds (Bible Scenario D must stay
    # Low). Urdu benign lines mix in at the same ratio as the scam bank, or
    # the model would learn "Urdu script == scam" and false-fire on Urdu chat.
    def benign_render() -> tuple[str, str]:
        if rng.random() < urdu_ratio:
            idx = rng.randrange(len(URDU_BENIGN))
            return URDU_BENIGN[idx], f"urdu_benign#{idx}"
        idx = rng.randrange(len(BENIGN))
        return _drift(BENIGN[idx], rng, rate=0.4), f"benign#{idx}"

    n_benign = max(per_label * 6, 600)
    for _ in range(n_benign):
        s, tid = benign_render()
        tids = [tid]
        if rng.random() < 0.20:
            frag, tid2 = benign_render()
            s = _compose(s, frag, rng)
            tids = sorted({tid, tid2})
        rows.append({"text": _casing(_keyboard_noise(s, rng), rng),
                     "labels": [], "template_ids": tids})

    rng.shuffle(rows)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/train/corpus.jsonl")
    ap.add_argument("--per-label", type=int, default=320)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--urdu-ratio", type=float, default=0.35,
                    help="fraction of renders drawn from URDU_TEMPLATES")
    args = ap.parse_args()

    rows = build_corpus(args.per_label, args.seed, urdu_ratio=args.urdu_ratio)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_pos = sum(1 for r in rows if r["labels"])
    n_multi = sum(1 for r in rows if len(r["labels"]) > 1)
    n_urdu = sum(1 for r in rows
                 if any(t.startswith("urdu_") for t in r["template_ids"]))
    print(f"wrote {len(rows)} samples -> {args.out}")
    print(f"  labelled       {n_pos}")
    print(f"  multi-label    {n_multi}")
    print(f"  benign         {len(rows) - n_pos}")
    print(f"  urdu-script    {n_urdu} ({n_urdu / len(rows):.0%} of rows)")
    print(f"  distinct labels {len(SCAM_LABELS | COUNTER_LABELS)}")


if __name__ == "__main__":
    main()
