#!/usr/bin/env python3
"""Golden-set authoring batch 2: scams gs_019..gs_035 (Bible Appendix E schema)."""
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

# utility (urdu) + tech support + employer + courier + authority
C("gs_019", "medium", "utility_impersonation", "urdu", [
 ("them", 0, "سوئی گیس ڈیپارٹمنٹ سے بول رہے ہیں۔ کل آپ کا میٹر چیکنگ کے لیے کھولا جائے گا، فیس دو ہزار روپے ہے۔"),
 ("me", 35, "چیکنگ کی فیس؟ پہلے کبھی نہیں تھی۔"),
 ("them", 18, "نیا قاعدہ ہے۔ فوراً ایجنٹ نمبر پر بھیج دیں ورنہ سپلائی کاٹ دی جائے گی۔"),
 ("me", 45, "میں آفس جانا چاہتا ہوں۔"),
 ("them", 12, "آفس والے نہیں ملیں گے۔ آج ہی فیس بھیجو، خبردار وقت پر نہ بھیجی تو نقصان آپ کا ہو گا۔"),
])
C("gs_020", "high", "tech_support_impersonation", "english", [
 ("them", 0,   "Hello sir, I am calling from Microsoft technical support department. Your computer is sending error reports to our server."),
 ("me",   32,  "Is it a virus? I do banking on that laptop!"),
 ("them", 20,  "Exactly why you must act now. Your bank app is compromised. We will fix it remotely."),
 ("them", 15,  "Install the remote app from this link: bit.ly/secure-fix-24 and enter the code I give you."),
 ("me",   50,  "Okay downloading it now."),
 ("them", 12,  "Good. Now read me the one-time password showing on your screen so I can complete the secure connection."),
])
C("gs_021", "high", "tech_support_impersonation", "mixed", [
 ("them", 0,   "WhatsApp official verification team. Aap ka account kal hack hone wala hai, security alert generate hua hai."),
 ("me",   30,  "Hack? Kaise pata chala?"),
 ("them", 16,  "System ne detect kiya. Bachane ke liye abhi jo 6-digit code SMS par aya hai woh mujhe bhej dein."),
 ("me",   40,  "Code aa gaya... 772310."),
 ("them", 10,  "Shukriya. Aur yeh raaste se apna WhatsApp backup bhi email kar dein, warna data delete ho jayega turant."),
])
C("gs_022", "high", "employer_recruiter_impersonation", "roman_urdu", [
 ("them", 0,   "Congrats! Aap ka CV shortlist hua hai Multinational Textiles ke liye. Main HR Manager Adnan bol raha hoon."),
 ("me",   30,  "Oh great! Kab interview hai?"),
 ("them", 18,  "Pehle onboarding complete karni hai. 5,000 ka refundable registration deposit chahiye, joining ke baad wapas."),
 ("them", 14,  "Ye EasyPaisa number hai: 0301-XXXXX44. Deposit ke baad appointment letter foran issue hota hai."),
 ("me",   48,  "Theek hai, shaam tak bhej deta hoon."),
 ("them", 10,  "Aaj hi karo, sirf 2 seats hain aur time nahi hai. HR group mein kisi ko batana nahi."),
])
C("gs_023", "medium", "employer_recruiter_impersonation", "english", [
 ("them", 0,   "Hi! We saw your profile on a jobs page. Work-from-home data entry — 4,000 PKR daily, paid every night."),
 ("me",   35,  "Sounds good, what is the catch?"),
 ("them", 18,  "No catch. You just pay a one-time advance deposit of 3,000 for your software license and portal login."),
 ("me",   42,  "Can the company deduct it from my first salary instead?"),
 ("them", 12,  "Company policy says no advance without deposit. Only 2 slots left today — decide fast."),
])
C("gs_024", "high", "courier_impersonation", "roman_urdu", [
 ("them", 0,   "TCS parcel service se call hai. Aap ka naam par London se parcel aaya hai jis mein currency hai."),
 ("me",   30,  "Parcel? Maine kuch order nahi kiya."),
 ("them", 18,  "Customs ne rok rakha hai. Release ke liye 6,200 customs duty foran jama karni hai."),
 ("them", 14,  "Ye agent number hai Easypaisa par: 0333-XXXXX12, reference parcel LC-8891 likh dein."),
 ("me",   46,  "Duty office se payment hoti thi na pehle?"),
 ("them", 11,  "Naya online system hai. 2 ghante ke andar fee na hui to parcel customs custody mein chale ga aur fine lage ga."),
])
C("gs_025", "medium", "courier_impersonation", "mixed", [
 ("them", 0,   "Leopard courier! Aap ke liye gift hamper aaya hai — iPhone aur perfume 🎁 Free hai bas delivery charges hain."),
 ("me",   28,  "Kaun bhej raha hai?"),
 ("them", 15,  "Surprise hai shayad koi apna. Sirf 950 rupay advance delivery fee hai, COD system change ho gaya."),
 ("me",   40,  "Address batao main khud le loon office se."),
 ("them", 12,  "Warehouse door hai sir, fee pehle online hogi phir address share hota hai. Jaldi karo offer expire ho raha hai."),
])

# authority_claim + romance + accidental transfer + OLX + investment + prize + remittance
C("gs_026", "medium", "authority_claim", "roman_urdu", [
 ("them", 0,   "Main Anti Corruption Officer Shahid bol raha hoon, badge number AC-2291."),
 ("them", 25,  "Aap ke ilaqay ke contractor par case hai aur aap gawah hain, official record mein naam aap ka aya hai."),
 ("me",   35,  "Gawah? Maine kuch dekha hi nahi."),
 ("them", 18,  "Record correction ke liye verification officer ID card number bhejo apna, case file update karne hai."),
 ("me",   44,  "ID number sensitive hota hai main khud office aa kar de deta hoon."),
 ("them", 12,  "Office aane ka time nahi hai. Turant photo bhejo warna summon nikal jaye ga, criminal case ban jaye ga."),
])
C("gs_027", "high", "romance", "mixed", [
 ("them", 0,   "Sorry galat number lag gaya tha, but aap ka intro dekh kar dil khush ho gaya 😊 Main Ahmed, Dubai mein kaam karta hoon."),
 ("me",   45,  "Haha koi baat nahi. Main Sana."),
 ("them", 60 * 60 * 8,  "Sana ji subah subah aap ki yaad aa gayi. Aaj din bohot acha ja raha hai alhamdulillah."),
 ("me",   120, "Aap to bohot sweet ho Ahmed 😄"),
 ("them", 90,  "Sach kahoon, itne kam dinon mein kisi ko itna close mehsoos nahi kiya. Yeh baat sirf tum se share kar raha hoon, kisi ko na batana."),
 ("them", 70,  "Aur suno, mere trading group mein gold signals se paisa double hota hai. Mere cousin ki car double ho gayi 2 mahine mein! Guaranteed profit hai risk zero."),
 ("me",   100, "Double?? Thora risky lagta hai sach mein."),
 ("them", 55,  "Bilkul nahi! Screenshots dekh lo mere profits ke. Entry aaj last day hai, 50,000 is Easypaisa manager account par: 0345-XXXXX77."),
 ("them", 25,  "Sirf 10 minute ke andar bhejo to VIP slot dilwa doonga. Time nahi hai jaan!"),
])
C("gs_028", "high", "romance", "roman_urdu", [
 ("them", 0,   "Jaan aaj bohot udaas tha office mein, sirf aap ki baaton ne sambhala 😔"),
 ("me",   50,  "Aww mere paas hi to ho, sab bataya karo."),
 ("them", 80, "Wahi to... ek secret share karoon? Main crypto futures mein trade karta hoon, is hafte $4000 kamaye."),
 ("me",   60, "Itne to hamare saal bhar ki salary nahi!"),
 ("them", 40, "Aap bhi join karo, main sikhaoonga step by step. Binance account banao aur pehle 30,000 dal do."),
 ("them", 30, "Aur please apni family ko abhi mat batana, shaadi se pehle unhein shock na ho. Trust me?"),
])
C("gs_029", "high", "romance", "english", [
 ("them", 0,   "My love, emergency!! I was detained at Karachi airport, they say my visa papers are fake."),
 ("me",   25,  "WHAT?! Are you okay?? Call me right now!"),
 ("them", 20,  "They took my phone at the counter, using an officer's phone only. I need 65,000 for immediate legal clearance or they move me to jail tonight."),
 ("them", 15,  "Send it by Western Union on my agent Mr. Tariq's name, this number: 0321-XXXXX09. Time nahi hai baby please."),
 ("me",   35,  "Sending right now! Don't worry, we'll sort this out."),
 ("them", 12,  "And baby please don't tell anyone, especially not your brother. If officials hear about outside calls it gets worse for me."),
])
C("gs_030", "critical", "accidental_transfer", "roman_urdu", [
 ("them", 0,   "Allah ka shukar! Bhai aap ne meri madad kar di, main ne galti se aap ke number par 40,000 bheje the aur aap ne lot diya 🙏"),
 ("me",   30,  "Haan yaar 40 hazar aye the, main hairan tha kis ke paise hain."),
 ("them", 18,  "Woh meri beti ki fees ke thay. Bhai ek urgent kaam — main ne aap ke number par 80,000 ghalati se bhej diye the kal raat."),
 ("me",   35,  "Nahi bhai, sirf 40 hazar aaye thay mere paas."),
 ("them", 15,  "Bank balance check karo! System ka masla hai, dono transactions ek sath gaye. Jo extra 40,000 hai woh wapas bhej do is IBAN par: PK36XXXX000034567890."),
 ("me",   50,  "Ek minute check karta hoon..."),
 ("them", 10,  "Foran bhai, bank branch 4 baje band ho jaye gi aur mera loan clear hona hai aaj hi. Meri izzat daav par hai."),
])
C("gs_031", "high", "olx_advance", "roman_urdu", [
 ("them", 0,   "Assalam o Alaikum, aap ki OLX listing dekhi Honda 125 ki. Paise tayyar hain full price par."),
 ("me",   30,  "Ji 145,000 final hai, bike Lahore mein hai."),
 ("them", 20,  "Main Islamabad se hoon, army mein hoon posting mein nahi aa sakta. Bike ship kara dein, main pehle advance de deta hoon."),
 ("them", 16,  "Sirf 5,000 booking fee hai jo OLX ke shipping partner ko deni hai, ye Easypaisa number: 0322-XXXXX88."),
 ("me",   45,  "OLX mein shipping service hoti hai? Mujhe to pata hi nahi."),
 ("them", 12,  "Naya service launch hua hai. Fee bhejte hi main full payment transfer kar deta hoon aaj hi, deal confirm karo turant."),
])
C("gs_032", "medium", "olx_advance", "mixed", [
 ("them", 0,   "Hi! I want to buy your iPhone listed on OLX. I'm out of country but my agent will pick it up."),
 ("me",   35,  "Sure, payment method? Cash on pickup preferred."),
 ("them", 20,  "I'll pay online through OLX wallet protection. Just buy a 4,000 PKR Google Play card and share the code as your identity verification."),
 ("me",   45,  "That sounds odd, why would identity need a Play card?"),
 ("them", 12,  "It unlocks your seller wallet, standard process now. Do it fast, another buyer is also interested."),
])
C("gs_033", "high", "investment_pitch", "roman_urdu", [
 ("them", 0,   "Bhai ek golden opportunity share karna chahta hoon, sirf close logon ko bata raha hoon."),
 ("them", 25, "Gold trading group hai Dubai se signals aate hain. Har member ne 2 mahine mein double kiya hai."),
 ("me",   35,  "Double? Kitne ka invest karna parta hai?"),
 ("them", 18, "Start 20,000 se. Guaranteed returns hain, admin khud insure karta hai. Daily profit screenshot group mein aata hai."),
 ("them", 16, "Aaj group band ho raha hai new members ke liye. 20,000 is account number par bhej do: PK00XXXX000055667788, slot lock ho jaye ga."),
 ("me",   45, "Ruk thora, main behen se pooch ke batata hoon."),
 ("them", 12, "Raat tak slots khatam. Aur bhai yeh group ka secret hai, kisi ko na batana warna membership cancel — rules hain."),
])
C("gs_034", "medium", "prize_lottery_claim", "mixed", [
 ("them", 0,   "EASY PAISA LUCKY DRAW 🎉 Aap ka number winner nikla hai 500,000 rupay ka! Reference EP-WIN-2026."),
 ("me",   30, "Maine to kabhi draw mein participate hi nahi kiya."),
 ("them", 18, "Automatic entry hoti hai sab customers ki. Claim karne ke liye 4,999 processing fee chahiye sirf."),
 ("them", 15, "Fee JazzCash par bhejein is merchant code par, prize same day release ho jata hai."),
 ("me",   42, "Prize ke liye fee? Ye to scam lagta hai."),
 ("them", 12, "Madam ye govt tax hai sirf naam ka. Aaj raat 12 baje tak claim na hui to prize next draw mein chala jaye ga."),
])
C("gs_035", "high", "remittance_request", "urdu", [
 ("them", 0, "السلام علیکم جناب، دبئی سے آپ کے دوست فیصل کا پیغام ہے۔ وہ مصروف ہیں اس لیے مجھے پیغام دیا۔"),
 ("me", 35, "فیصل؟ اچھا بتائیں۔"),
 ("them", 20, "ان کا کاروباری سودا کل فائنل ہونا ہے اور ان کا بینک ٹرانسفر رک گیا ہے۔ آپ فوری طور پر تین لاکھ روپے میری کمپنی اکاؤنٹ میں بھیج دیں۔"),
 ("me", 45, "اتنے پیسے؟ میں پہلے خود فیصل سے بات کرتا ہوں۔"),
 ("them", 15, "وہ فلائٹ پر ہیں کوئی کال نہیں لگا سکتے۔ ویسترن یونین سے بھیجیں، سودا ڈوب جائے گا ورنہ۔ جلدی کریں آج کی آخری ٹائم ہے۔"),
])

with open(os.path.join(OUT, "_manifest_batch2.json"), "w") as fh:
    json.dump([c["id"] for c in CONVS], fh)
for c in CONVS:
    with open(os.path.join(OUT, f"{c['id']}.json"), "w") as fh:
        json.dump(c, fh, ensure_ascii=False, indent=2)
print(f"wrote {len(CONVS)} conversations -> {OUT}")
