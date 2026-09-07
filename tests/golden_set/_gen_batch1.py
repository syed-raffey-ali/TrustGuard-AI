#!/usr/bin/env python3
"""Golden-set authoring batch 1: scams gs_001..gs_018 (Bible Appendix E schema)."""
import json, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)))
CONVS = []

def C(cid, band, family, lang, msgs, channel="text", label="scam"):
    CONVS.append({
        "id": cid, "label": label, "expected_band": band, "family": family,
        "language": lang, "channel": channel,
        "messages": [
            {"message_id": f"m_{i+1}", "speaker": s,
             "timestamp_offset_s": sum(x[1] for x in msgs[:i]),
             "text": t.strip()}
            for i, (s, g, t) in enumerate(msgs)
        ],
    })

# ---- bank_impersonation cluster (>=5 bank/OTP required overall) -------------------
C("gs_001", "critical", "bank_impersonation", "roman_urdu", [
 ("them", 0,   "Assalam o Alaikum, main ApnaBank fraud department se bol raha hoon, officer ID AB-4471."),
 ("them", 25,  "Aap ke account se 50,000 rupay ka suspicious transaction detect hua hai."),
 ("me",   30,  "Transaction? Maine to kuch nahi kiya!"),
 ("them", 15,  "Isi liye to call ki hai. Rokne ke liye verification zaroori hai turant."),
 ("them", 12,  "Abhi aap ko ek OTP bheja ja raha hai, woh code batao mujhe."),
 ("me",   40,  "Code aa gaya hai..."),
 ("them", 10,  "Foran batao, account block hone se pehle! Kisi ko na batana yeh confidential matter hai."),
])
C("gs_002", "critical", "bank_impersonation", "english", [
 ("them", 0,   "Hello, this is Metro Commercial Bank security department. There is an unauthorized transfer attempt on your savings account."),
 ("me",   35,  "Oh no, what should I do?"),
 ("them", 18,  "We can block it right now. We have sent a one-time password to your registered number."),
 ("them", 10,  "Read me the OTP so I can cancel the transaction immediately."),
 ("me",   45,  "Wait, should I not call the branch first?"),
 ("them", 8,   "There is no time! Within 5 minutes the money will be gone. Do not tell anyone, this is a confidential investigation."),
])
C("gs_003", "critical", "bank_impersonation", "urdu", [
 ("them", 0,   "السلام علیکم، میں اپنا بینک کے فراڈ ڈیپارٹمنٹ سے بول رہا ہوں۔ آپ کے اکاؤنٹ سے پیسے کٹنے کی کوشش ہوئی ہے۔"),
 ("me",   40,  "اللہ! پھر کیا کرنا ہے؟"),
 ("them", 20,  "فوراً ویریفیکیشن کوڈ بتائیں جو ابھی آپ کو ایس ایم ایس آ رہا ہے۔"),
 ("them", 12,  "جلدی کریں، دس منٹ کے اندر اکاؤنٹ بلاک ہو جائے گا۔"),
 ("me",   50,  "کوڈ آ گیا ہے، ۴۴۳۲۱۔"),
 ("them", 9,   "شکریہ۔ کسی کو نہ بتانا اس بارے میں، خفیہ تفتیش چل رہی ہے۔"),
])
C("gs_004", "high", "bank_impersonation", "mixed", [
 ("them", 0,   "ApnaBank helpline yahan se. Sir aap ki card expiry update nahi hui, payments decline ho rahi hain."),
 ("me",   30,  "Haan actually do baar decline hua tha kal."),
 ("them", 20,  "Exactly! Card number confirm kar dein aur jo PIN use karte ho woh bhi batao, hum nayi chip activate kar dete hain."),
 ("me",   55,  "PIN share karna zaroori hai?"),
 ("them", 12,  "Bilkul, warna card permanent block ho jayega. Turant karo."),
])

# ---- government_impersonation ----------------------------------------------------
C("gs_005", "high", "government_impersonation", "roman_urdu", [
 ("them", 0,   "Yeh FBR tax office ka call hai. Aap ke naam par tax fraud ka case darj hua hai, case number TX-99213."),
 ("me",   40,  "Fraud? Maine kabhi tax chhupaya nahi!"),
 ("them", 22,  "Proof humare paas hai. Arrest warrant jari ho gaya hai, police kal subah aayegi."),
 ("them", 15,  "Case khatam karne ke liye abhi 25,000 rupay fine jama karo is account number par: PK00XXXX000011223344."),
 ("me",   60,  "Itni si baat? Theek hai bhejta hoon magar time milta hai?"),
 ("them", 10,  "Aaj hi within 2 hours, warna greftar ho gi. Kisi lawyer se baat na karna."),
])
C("gs_006", "high", "government_impersonation", "urdu", [
 ("them", 0,   "میں نادرا آفس سے بول رہا ہوں۔ آپ کا شناختی کارڈ دھوکہ دہی کے لیے استعمال ہوا ہے۔"),
 ("me",   45,  "یہ کیسے ممکن ہے؟"),
 ("them", 20,  "سِمز آپ کے نام پر ریجسٹرڈ ہیں۔ تحقیقات کے لیے فوراً اپنا CNIC نمبر اور ماں کا نام بتائیں۔"),
 ("me",   35,  "کیا یہ برانچ میں ہو سکتا ہے؟"),
 ("them", 14,  "وقت نہیں ہے۔ ابھی بتائیں ورنہ تمام سِم بلاک کر دی جائیں گی اور فوجی کیس بنے گا۔"),
])
C("gs_007", "medium", "government_impersonation", "mixed", [
 ("them", 0,   "Police cybercrime cell. Ek complaint aap ke number se offensive content post karne par aayi hai."),
 ("me",   35,  "Maine kuch post nahi kiya, mera phone hack ho sakta hai!"),
 ("them", 20,  "Charges hatane ke liye verification officer se milna hoga. Pehle 15,000 ka processing fee bhejo JazzCash par."),
 ("me",   50,  "Mujhe station aa kar milna chahta hoon."),
 ("them", 12,  "Station aaoge to seedha remand mein jao ge. Abhi turant fee bhejo aur case khatam karo."),
])

# ---- wallet_impersonation ---------------------------------------------------------
C("gs_010", "critical", "wallet_impersonation", "roman_urdu", [
 ("them", 0,   "Hello! Main Easypaisa ka authorized agent hoon, aap ne hamara survey fill kiya tha."),
 ("them", 30,  "Aap 25,000 rupay ka lucky draw jeet gaye hain! 🎉"),
 ("me",   35,  "Sach mein?! Kaise milenge paisay?"),
 ("them", 15,  "Pehle 2,500 ka tax token jama karo phir prize release hota hai turant."),
 ("them", 12,  "Ye raasta number hai, is Easypaisa merchant account par bhej dein: 0341-XXXXX90."),
 ("me",   45,  "Theek hai, bhej deta hoon abhi."),
 ("them", 10,  "Jaldi karo, offer aaj hi expire hota hai. Kisi ko na batana warna prize cancel."),
])
C("gs_011", "high", "wallet_impersonation", "mixed", [
 ("them", 0,   "JazzCash fraud team here. Someone tried to empty your wallet from Lahore."),
 ("me",   30,  "Ya Allah! Mera to balance hi nahi tha zyada."),
 ("them", 18,  "Wallet freeze karne ke liye hum ne aap ko OTP bheja hai, read it back to me."),
 ("me",   40,  "OTP aa gaya 88123."),
 ("them", 10,  "Shukriya madam. Aur apna 5-digit MPIN bhi de dein taake security set kar sakein permanently."),
])
C("gs_012", "medium", "wallet_impersonation", "roman_urdu", [
 ("them", 0,   "Assalam o Alaikum, Raast payment agent. Aap ko government ki relief wali 12,000 rupay milegi."),
 ("me",   40,  "Kis scheme ki baat kar rahe hain?"),
 ("them", 18,  "Ehsaas program. Bas pehle 500 registration fee bhejo, phir 12 hazar foran aayenge."),
 ("me",   55,  "Fee kyun? Relief to free hoti hai."),
 ("them", 12,  "Madam system mein fee ke baghair entry nahi hoti. Aaj last day hai, jaldi karo."),
])

# ---- family_impersonation ----------------------------------------------------------
C("gs_013", "high", "family_impersonation", "mixed", [
 ("them", 0,   "Assalam o Alaikum Abu ji, main Bilal bol raha hoon aap ka beta."),
 ("me",   30,  "Beta kahan se call kar rahe ho? Awaz change lag rahi hai."),
 ("them", 18,  "Mere paas naya number hai purana kho gaya. Abu main Dubai airport phansa hoon, visa issue hai."),
 ("them", 15,  "Mujhe 80,000 rupay urgent bhejne hain agent ko, warna jail ho jaye gi. Please kisi ko na batana, ammi ko mat batana."),
 ("me",   50,  "Allah ke kasam sach keh rahe ho beta?"),
 ("them", 10,  "Abu main sach mein phansa hoon, foran bhejo is number par. Baad mein sab samjhata hoon."),
])
C("gs_014", "medium", "family_impersonation", "urdu", [
 ("them", 0,   "آپ کا بھائی میرے پاس ہے، وہ مشکل میں پھنس گیا ہے۔"),
 ("me",   35,  "کس بھائی کی بات کر رہے ہو؟ پہلے نام بتاؤ۔"),
 ("them", 18,  "وقت نہیں ہے! پیسے چاہئیں ابھی، ورنہ بہت برا ہو گا۔ ایزی پیسہ پر 30 ہزار بھیجو۔"),
 ("me",   45,  "پہلے اس کی آواز سناؤ تو۔"),
 ("them", 12,  "وہ بول نہیں سکتا، زخمی ہے! جلدی کرو ورنہ معاملہ خراب ہو جائے گا۔"),
])
C("gs_015", "high", "family_impersonation", "roman_urdu", [
 ("them", 0,   "Aunty main Zoya ke office se bol rahi hoon. Zoya bohot bimar hai hospital mein admit hai."),
 ("them", 28,  "Unhein foran operation karna hai, 150,000 deposit chahiye abhi."),
 ("me",   40,  "Allah! Kaun sa hospital hai beta?"),
 ("them", 15,  "Private hospital hai. Western Union se bhej dein mere cousin ke naam par, pata yeh hai."),
 ("them", 12,  "Please aunty Zoya ko phone mat karna woh unconscious hai, aur family ko mat batana sharam ki baat hai."),
])

# ---- telecom_impersonation -----------------------------------------------------------
C("gs_016", "high", "telecom_impersonation", "mixed", [
 ("them", 0,   "PTA se official call hai. Aap ke CNIC par registered 6 SIMs hain jin ka misuse ho raha hai."),
 ("me",   32,  "Sirf 2 SIM meri hain to baaki kiski?"),
 ("them", 18,  "Wahi to problem hai. Block karwane ke liye hum ne aap ko verification code bheja hai."),
 ("them", 12,  "Code yahan type kar dein ya bata dein, main note kar leta hoon."),
 ("me",   42,  "Code 55098 aa gaya."),
 ("them", 10,  "Perfect. Ab biometric verify karne ke liye 999 rupay charge bhejein Easypaisa se, process turant start hoga."),
])
C("gs_017", "medium", "telecom_impersonation", "roman_urdu", [
 ("them", 0,   "Congratulations! Aap Telenor ke customer loyalty draw mein jeet gaye hain — 100,000 rupay!"),
 ("me",   35,  "Yaar phir se lottery scam?"),
 ("them", 15,  "Nahi madam yeh official hai. Sirf 1,500 ka SIM verification fee hai, balance aap ke account mein aayega."),
 ("me",   50,  "Fee maaf kar do phir manon gi."),
 ("them", 12,  "Fee ke baghair process nahi hota. Aaj raat 12 baje tak bhejo warna next winner ko chala jaye ga."),
])

# ---- utility_impersonation -------------------------------------------------------------
C("gs_018", "medium", "utility_impersonation", "roman_urdu", [
 ("them", 0,   "WAPDA billing office se baat kar raha hoon. Aap ka bijli bill 3 mahin se pending hai."),
 ("me",   30,  "Bill to main ne jama kiya tha copy ke sath."),
 ("them", 18,  "Record mein pending hai. Connection aaj raat 8 baje kat jaye ga."),
 ("them", 12,  "Turant 8,400 rupay technician ko is Easypaisa number par bhejo, reconnection foran hoga."),
 ("me",   45,  "Office ja kar clear kar loonga main."),
 ("them", 10,  "Office band ho jaye ga 5 baje. Jaldi karo, warning sirf ek baar de raha hoon."),
])

with open(os.path.join(OUT, "_manifest_batch1.json"), "w") as fh:
    json.dump([c["id"] for c in CONVS], fh)
for c in CONVS:
    with open(os.path.join(OUT, f"{c['id']}.json"), "w") as fh:
        json.dump(c, fh, ensure_ascii=False, indent=2)
print(f"wrote {len(CONVS)} conversations -> {OUT}")
