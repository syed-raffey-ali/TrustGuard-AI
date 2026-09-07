#!/usr/bin/env python3
"""Fill-in: gs_008 (voice_transcript) + gs_009 to complete the 35-scam quota."""
import json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)))

def W(cid, band, family, lang, msgs, channel="text", label="scam"):
    conv = {
        "id": cid, "label": label, "expected_band": band, "family": family,
        "language": lang, "channel": channel,
        "messages": [
            {"message_id": f"m_{i+1}", "speaker": s,
             "timestamp_offset_s": sum(x[1] for x in msgs[:i]),
             "text": t.strip()}
            for i, (s, g, t) in enumerate(msgs)
        ],
    }
    with open(os.path.join(OUT, f"{cid}.json"), "w") as fh:
        json.dump(conv, fh, ensure_ascii=False, indent=2)

# voice transcript of the flagship call scenario (as STT would render it)
W("gs_008", "critical", "bank_impersonation", "mixed", [
 ("them", 0,   "Hello? Hello madam main ApnaBank fraud department se bol raha hoon."),
 ("them", 8,   "Madam aap ke account se pachaas hazaar rupay nikalne ki koshish hui hai online."),
 ("me",   6,   "Nahi nahi main ne kuch nahi bheja!"),
 ("them", 5,   "Ji bilkul isi liye main ne call kiya hai. Rokne ke liye hum ne aap ko ek code bheja hai SMS par."),
 ("them", 7,   "Woh verification code mujhe read kar dein abhi, transaction foran cancel hoti hai."),
 ("me",   9,   "Theek hai ek minute... code aa gaya 55210."),
 ("them", 6,   "Perfect madam. Aur yeh baat kisi ko na batana, na family ko na bank branch ko, confidential case hai."),
], channel="voice_transcript")

# bank impersonation + account-number harvesting variant
W("gs_009", "high", "bank_impersonation", "roman_urdu", [
 ("them", 0,   "Metro Commercial Bank ki taraf se salam. Aap ke dormant account ka refund 95,000 rupay clear ho gaya hai."),
 ("me",   30,  "Refund? Kaunsa account bhai?"),
 ("them", 18,  "Purana salary account jo 2019 se band hai. Refund chahiye to apna active IBAN/account number confirm kar dein."),
 ("them", 15,  "Aur mobile banking PIN bhi update kar dein taake transfer turant ho jaye."),
 ("me",   40,  "PIN bhi dena zaroori hai?"),
 ("them", 11,  "Ji system requirement hai. Jaldi karein refund queue kal tak expire ho jati hai."),
])

print("wrote gs_008.json gs_009.json")
