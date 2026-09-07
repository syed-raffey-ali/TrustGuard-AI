# TrustGuard AI / R CHAT — Complete Setup & Testing Guide

Everything you need to run, demo, and test the whole system yourself.

---

## 1. What you have

**R CHAT** is a WhatsApp-style Android messaging + calling app with a live
scam-detection engine running behind it. Every message and every second of
call audio is analysed in real time; when a scam is detected the phone
vibrates and shows a coloured alert banner with the exact reason.

| Piece | What it is |
|---|---|
| **R CHAT APK** (18 MB) | `apps/android/app/build/outputs/apk/debug/app-debug.apk` — accounts, chat, voice calls, scam alerts, live call captions |
| **Gateway** (port 8080) | The brain: FastAPI + WebSockets, the scoring engine, STT, accounts |
| **Detection engine** | 3 tiers + caller-ID verification (see §2) |
| **Web dashboard** | Live view of every session, score, band, signals |
| **Bank directory** | `data/bank_directory.json` — 59 real Pakistani organisations, official numbers, scam patterns |

### Detection performance (golden set, 60 conversations)

| Metric | Value | Meaning |
|---|---|---|
| Recall | **97.5%** | catches 97 of 100 real scams |
| Precision | **95.1%** | when it says "scam", it's right 95 times of 100 |
| F1 | **96.3%** | overall balance |
| Band accuracy (±1) | **91.7%** | severity level correct |
| Prompt-injection defence | **PASS** | scammer cannot talk the AI out of warning you |

Languages: **English, Roman Urdu (WhatsApp-style Urdu in English letters),
and Urdu script** — mixed in the same call is fine.

---

## 2. How detection works (the 5 layers)

```
phone audio ──► faster-whisper (speech→text, ~1.7x realtime)
                      │
                      ▼ transcript
   Tier 1   regex rules              < 1 ms   (cap: score 24)
   Tier 15  trained ML classifier    0.25 ms  (cap: score 74)  ← 22,839 samples
   Tier 2   cloud LLM (5 providers)  2-20 s   (cap: score 100)
   Caller-ID bank directory          < 1 ms   (HBL claimed but mobile number? +hit)
                      │
                      ▼
   deterministic scorer (the ONLY score producer)
   low 0-24 | medium 25-49 | high 50-74 | critical 75-100
```

- **Fast path**: the moment new speech is transcribed, Tier-1 + ML + caller-ID
  score it in under 100 ms — the first warning usually appears **8-14 s** after
  the scammer speaks.
- **Confirmed path**: every ~3 s the cloud LLM re-scores the conversation; a
  critical alert (75+) requires this confirmation.
- **Ratchet**: the score can never drop more than 5 points per cycle — a
  scammer can't talk the warning away by changing the subject.
- **Privacy**: raw audio lives only in a rolling in-memory buffer and is
  deleted when the call ends. Only the transcript and score are stored.

---

## 3. One-time setup

Prerequisites (already done on this machine — this is for a fresh setup):

```bash
cd trustguard-ai
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # includes faster-whisper
```

API keys live in **`.env`** (never commit it). Current providers, in failover
order:

| Provider | Model | Status |
|---|---|---|
| groq | openai/gpt-oss-120b | works (200k tokens/day free) |
| gemini | gemini-3.1-pro-preview | dead (no free quota) — system skips it |
| openrouter_stealth | stealth/ox-alpha | primary failover |
| openrouter_minimax | minimax/minimax-m3:free | primary workhorse |
| openrouter_nemotron | nvidia/nemotron-3-super-120b-a12b:free | backup |

If one provider dies (429/5xx), the gateway **automatically fails over** to the
next one. Add new keys to `.env` (e.g. `GROQ_API_KEY=...`) and restart the
gateway — no code changes needed.

STT model is configured with `STT_MODEL=base` (balanced). Use `tiny` for
maximum speed on weak CPUs, `small` for best accuracy on strong machines.

---

## 4. Start everything

```bash
cd trustguard-ai

# 1. gateway (API + WebSocket + STT + scoring)  — keep this running
bash scripts/run_gateway.sh
#    → http://0.0.0.0:8080   (check: curl localhost:8080/health)

# 2. web dashboard (optional, for the big-screen demo)
cd apps/web/dashboard && npm run dev
#    → http://localhost:5173
```

The gateway loads `.env` itself — just run the script.

---

## 5. Install R CHAT on Android phones

The APK is already built:

```
trustguard-ai/apps/android/app/build/outputs/apk/debug/app-debug.apk
```

Install (phone connected via USB with USB debugging on, or copy the file and
open it on the phone):

```bash
adb install -r apps/android/app/build/outputs/apk/debug/app-debug.apk
```

Works on **any Android 8.0+ phone** (minSdk 26). Rebuild from source:

```bash
cd apps/android && /home/raff/gradle-8.9/bin/gradle assembleDebug
```

**Point the app at your gateway** (Settings, gear icon):
- Emulator: `http://10.0.2.2:8080`
- Physical phones on the same Wi-Fi: `http://<your-laptop-LAN-IP>:8080`
  (find it with `ip addr` — e.g. `http://192.168.1.20:8080`)

Permissions the app asks for: **Microphone** (call audio), **Notifications**
(alerts while in background). Both are requested on first call.

---

## 6. Test messaging + detection (two accounts)

1. On phone A: open R CHAT → **Sign up** → username `ali`, password.
2. On phone B: sign up as `sara`.
3. Both phones: the roster shows the other user (refresh icon).
4. Tap the contact → **Chat**. Messages deliver live with ticks.
5. **Scam test over chat** — from phone B type:

   ```
   Assalam o alaikum main HBL bank security se call kar raha hoon.
   Aap ke account se suspicious transaction hui hai.
   Account block ho jayega, jo OTP aya hai turant bata dein.
   ```

   Within ~2-5 s phone A shows the **amber → orange alert banner** with
   reasons ("Asking for an OTP", "Impersonating your bank", …) and a safe
   action. A safe conversation stays green/"Protected".
6. The banner has **"I've verified this contact"** — it hides the alert until
   the risk *escalates* (dismissal is reported to the dashboard).

Every chat message gets: instant on-device Tier-1 ack (<150 ms) + server
analysis with ML + cloud confirmation.

---

## 7. Test LIVE CALL detection (the main demo)

1. From the roster, tap the contact → **Call** (phone icon).
2. The other phone rings-style shows "Connecting…", audio flows both ways.
3. You will see on the call screen:
   - **"This call is being analysed"** pill
   - **Live transcript** card — the other side's speech appears as text
     (this is faster-whisper running on your laptop, live)
   - **Shield indicator** in the header (green → coloured when risk rises)
4. **Scam script to read aloud** (the caller role, in any mix of Urdu/English):

   ```
   Hello sir, this is HBL bank security department.
   We have detected a suspicious transaction on your account.
   Your account will be blocked within one hour.
   Please tell me the OTP code you received on your phone right now.
   ```

   Timeline you'll see: first alert ~8-14 s after you start speaking
   (ML fast path, amber), then **CRITICAL red banner + strong vibration
   pattern** once the cloud LLM confirms (~10-20 s more).
5. Safe chat ("chal kal milte hain, chai peene chalenge") → stays green.
6. **Hang up** cleanly with the red button; the other side is notified.

Vibration patterns: medium = short pulse, high = double pulse,
critical = waveform (long-short-long). Vibrate permission is not needed on
modern Android for these.

**Single-phone demo**: call from the app to the same account on an emulator,
or use the scripted tests in §9 — no second phone needed.

---

## 8. Caller-ID verification demo

When a session registers a caller number, every scoring cycle checks the
bank directory:

- Caller **claims to be from HBL** (in speech or chat) but the number is a
  mobile (`+92 300…`) → extra `bank_impersonation` hit + a warning like
  *"Caller claims to be from HBL, but this number is not an official HBL
  line. HBL never asks for OTPs… Hang up and call 111-111-425 directly."*
- Caller claims HBL **from the real helpline number** → no penalty.

59 organisations covered: all scheduled banks (HBL, UBL, MCB, ABL, Meezan,
Alfalah, Askari, Faysal, SC, NBP, BOP, …), wallets (Easypaisa, JazzCash,
SadaPay, NayaPay), telcos (Jazz, Zong, Telenor, Ufone), government (NADRA,
FBR, PTA), KE/SNGPL/Sui, couriers (TCS, Leopard's) and more.

---

## 9. Run the test suites yourself

With the gateway running (`bash scripts/run_gateway.sh`):

```bash
# golden-set evaluation — 60 conversations, live cloud calls (~4 min)
PYTHONPATH="services:services/realtime-gateway" .venv/bin/python scripts/eval.py

# live voice-flow test — transcript segments through the full pipeline
.venv/bin/python scripts/test_voice_flow.py

# FULL AUDIO test — synthesized scam speech streamed as PCM over WebSocket:
# whisper transcribes it, captions + critical alert appear. Best proof!
.venv/bin/python scripts/test_voice_audio.py

# unit tests (scoring engine, 11 tests)
PYTHONPATH="services:services/realtime-gateway" .venv/bin/python -m pytest tests/test_scoring.py -q
```

The audio test prints a live timeline like:

```
[caption  13.9s] (them) Hello Sir, this is HBO Bank Security Department calling you Sir.
[risk     13.9s] score=12.4 band=low  signals=['bank_impersoning', ...]
[risk     36.0s] score=77.8 band=critical signals=['otp_harvesting', ...]
AUDIO E2E: PASS
```

---

## 10. Dashboard live view

Open `http://localhost:5173` (dev server) — it shows live sessions, scores,
bands and signal cards as conversations happen. Run any test from §9 or use
the phones; events appear instantly over the dashboard WebSocket.

---

## 11. API / token usage (free-tier planning)

Rough numbers from this machine:

- **Tier-2 LLM**: ~600-900 input + ~150 output tokens per scoring cycle,
  one cycle per conversation update (chat: 1 s debounce; call: 3 s cycle).
  A **12-minute scam call** with continuous speech ≈ 40-80 cycles ≈
  **~50-100k tokens** total across providers.
- **STT / ML / rules / caller-ID**: run on your laptop, **zero API cost**.
- **Groq free tier**: 200k tokens/day (enough for ~2-4 heavy calls/day).
- **OpenRouter free models**: ~50-1000 requests/day per model depending on
  load — that's why 3 OpenRouter models are configured with failover.

When everything is rate-limited the system still works: Tier-1 + ML +
caller-ID keep scoring (capped at "High" without cloud confirmation).

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `faster-whisper not installed` in gateway log | `.venv/bin/python -m pip install faster-whisper` and restart |
| Phones can't connect | Same Wi-Fi, gateway URL is the laptop's LAN IP, firewall allows 8080 (`sudo ufw allow 8080`) |
| No alerts during calls | Check the call screen shows "This call is being analysed"; speak louder/closer; first transcription after gateway start takes ~10 s (model load) |
| All cloud models 429 | Daily free quota exhausted — detection still works on ML+rules tier; add another key to `.env` |
| Scores feel too low/high per band | Bands: low 0-24, medium 25-49, high 50-74, critical 75-100 — ML alone can reach 74, critical needs cloud confirmation |
| Rebuild APK | `cd apps/android && /home/raff/gradle-8.9/bin/gradle assembleDebug` |

---

## 13. File map (where things live)

```
trustguard-ai/
├── .env                          # API keys + model config (never commit)
├── data/bank_directory.json      # 59 orgs, official numbers, scam patterns
├── data/models/tier15_*.joblib   # trained ML model (F1 0.815)
├── services/
│   ├── realtime-gateway/         # THE gateway: main.py, ws.py, pipeline.py,
│   │                             #   accounts.py, stt_stream.py, caller_id
│   ├── scoring/                  # engine.py (sole score producer), taxonomy,
│   │                             #   rules_engine.py, caller_id.py
│   ├── ai/tier2.py               # 5 cloud providers + failover + race
│   ├── ml/                       # datagen.py, train.py, classifier.py, augment.py
│   └── stt/service.py            # faster-whisper wrapper
├── apps/android/                 # R CHAT (Kotlin + Compose)
├── apps/web/dashboard/           # live monitoring dashboard
├── scripts/                      # run_gateway.sh, eval.py, test_voice_*.py
└── tests/golden_set/             # 60 evaluation conversations
```
