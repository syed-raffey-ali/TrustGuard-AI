# TrustGuard AI

### Catching scams before the money moves

TrustGuard AI is a privacy-first scam interception prototype for calls, SMS, and chats. It is designed to sit inside a bank or fintech app and help a person recognize manipulation before an OTP, PIN, card number, or transfer is shared.

The project focuses on the part of fraud that conventional banking systems usually see too late: the conversation that persuades a victim to make a dangerous decision.

> Built for the Alibaba Cloud AI Hackathon Pakistan 2026.

## The idea

A modern scam rarely stays in one channel. A fake bank officer may call, a real-looking OTP may arrive by SMS, and a follow-up chat may create urgency. TrustGuard correlates those signals instead of treating each message as an isolated event.

The prototype combines:

- Caller and number context.
- Tier-1 deterministic rules for fast, auditable detections.
- A trained local taxonomy classifier.
- Optional local Ollama inference.
- Optional cloud model comparison across OpenAI-compatible providers.
- Cross-channel call, SMS, and chat evidence.
- Explainable scores with quoted evidence.
- Safe actions such as hanging up, independent verification, reporting, blocking, and demo account freezing.
- Urdu, Roman Urdu, and English-oriented scam patterns.

## Why it matters

Banks and payment systems are excellent at reacting to suspicious money movement. TrustGuard targets the earlier moment when a scammer is building authority, fear, urgency, secrecy, or false trust.

The goal is not silent surveillance. The demo is designed around user-owned sessions, an analysis indicator, server-side provider keys, no raw-audio persistence, and fictional bank data.

## What is implemented

### Android client

The Kotlin and Jetpack Compose app includes registration, device roster, chat, calls, notifications, settings, Director Mode, on-device Tier-1 checks, risk banners, and safe-action flows.

The demo APK is available at [`artifacts/RCHAT.apk`](artifacts/RCHAT.apk).

### Realtime gateway

The FastAPI gateway provides REST and WebSocket APIs for:

- Chat and call sessions.
- Live risk updates.
- Transcript segments and voice transport.
- Cross-channel session linking.
- Session history, reports, evidence, and model comparisons.
- Provider administration.
- Paste analysis.
- Demo bank safe-action endpoints.

### Mission-control dashboard

The React, TypeScript, and Vite dashboard exposes:

- Live sessions, transcripts, risk gauges, signal breakdowns, and timelines.
- Evidence history with contribution scores and quoted messages.
- Model Race latency and result comparison.
- Provider registry and provider testing.
- Plain-text and WhatsApp-export Paste Analyzer workflows.
- Privacy and consent principles.
- Telemetry for sessions, devices, latency, parsing failures, and ML evaluation.

### Detection pipeline

The scoring path is deliberately layered:

1. **Tier 1:** deterministic rules provide fast signals such as OTP harvesting, bank impersonation, urgency, secrecy, threats, and authority claims.
2. **ML taxonomy:** the bundled `data/models/tier15_taxonomy.joblib` classifier adds trained local labels.
3. **Tier 2:** optional local Ollama and cloud providers provide additional interpretation and model comparison.
4. **Deterministic scoring:** the final displayed score, band, evidence, and safe actions remain controlled by backend scoring logic rather than an unconstrained model response.

## Architecture

```text
Android demo app(s)
        |
        | REST + WebSocket
        v
FastAPI realtime gateway :8080
        |
        +--> Tier-1 rules + trained local taxonomy
        +--> Optional Ollama model
        +--> Optional cloud provider race
        +--> STT for voice sessions
        +--> Deterministic score, evidence, and safe actions
        |
        +--> React mission-control dashboard :5173
        +--> Fictional demo-bank service :8002
```

## Quick start

### Requirements

- Python 3.12 or newer.
- Node.js 20 or newer and npm.
- `curl` for setup health checks.
- Ollama is optional for local Tier-2 inference.
- Android Platform Tools (`adb`) are optional for automatic APK installation.
- A cloud API key is optional. The deterministic and bundled local tiers work without one.

### One-command setup

From the repository root:

```bash
./setup_and_run.sh
```

The setup runner:

1. Checks the required tools and project artifacts.
2. Creates a local `.venv`.
3. Installs the Python requirements.
4. Installs the locked web dependencies with `npm ci`.
5. Creates a local SQLite `.env` from `.env.example` when needed.
6. Reports whether cloud API keys are configured.
7. Detects Ollama and downloads `qwen2.5:3b-instruct` by default when Ollama is installed.
8. Explains that the Whisper model is downloaded by `faster-whisper` on first voice use.
9. Starts the gateway and dashboard.
10. Checks `/health` and the dashboard HTTP response.
11. Installs `artifacts/RCHAT.apk` when an Android device or emulator is connected through `adb`.

To skip the approximately 1.9 GB Ollama download:

```bash
INSTALL_OLLAMA_MODEL=0 ./setup_and_run.sh
```

The large Ollama and Whisper runtime models are intentionally downloaded during setup rather than committed to GitHub. The trained taxonomy artifact required by the local scoring path is already included.

### API keys

Cloud providers are optional. To enable them, copy the safe template and add keys locally:

```bash
cp .env.example .env
# edit .env and add one or more provider keys
```

Supported configuration includes Alibaba Model Studio, Groq, Gemini, OpenRouter, custom OpenAI-compatible endpoints, and Ollama. Never commit `.env`, provider credentials, or keys inside the APK.

### Manual services

Gateway:

```bash
bash scripts/run_gateway.sh
```

Dashboard:

```bash
cd apps/web/dashboard
npm ci
npm run dev
```

The dashboard opens at `http://localhost:5173` and the gateway health endpoint is `http://localhost:8080/health`.

## Android setup and gateway connection

Install the APK with Android Studio or:

```bash
adb install -r artifacts/RCHAT.apk
```

Start the gateway on the computer that will act as the server. In the Android app, open **Settings** and set the gateway URL:

- Android emulator: `http://10.0.2.2:8080`
- Physical phone: `http://<SERVER_LOCAL_IP>:8080`

The server local IP is the IPv4 address of the computer running TrustGuard, for example `192.168.1.20`. Find it on Linux with:

```bash
hostname -I
# or
ip -4 addr
```

The phone and computer must be on the same network, and the firewall must allow TCP port `8080`. For two-phone demos, install the APK on both devices and point both apps at the same gateway. Register each device, select the other device, and use Chat or Call.

## Demo walkthrough

1. Start the gateway and dashboard.
2. Open the dashboard at `http://localhost:5173`.
3. Install `RCHAT.apk` on one or two devices, or use Director Mode for a phone-free demo.
4. Run the safe scenario to show a low-risk conversation.
5. Run a bank impersonation scenario to show evidence-backed high risk.
6. Run the call plus OTP scenario to show cross-channel escalation.
7. Open Evidence to inspect quoted messages and score history.
8. Open Model Race to compare provider latency and outcomes.
9. Open Providers to test an available provider.
10. Open Paste Analyzer and try both plain text and WhatsApp export formats.
11. Open Privacy to explain the consent and data-retention boundaries.

The completed dashboard captures are documented in [`demo/README.md`](demo/README.md).

## Demo scenarios

The phone-free replay script drives the real gateway:

```bash
.venv/bin/python scripts/demo_replay.py --scenario A --speed 4  # safe conversation
.venv/bin/python scripts/demo_replay.py --scenario B --speed 4  # call + OTP cross-channel
.venv/bin/python scripts/demo_replay.py --scenario C --speed 4  # grooming pattern
.venv/bin/python scripts/demo_replay.py --scenario D --speed 4  # safe false-positive check
.venv/bin/python scripts/demo_replay.py --scenario E --speed 4  # prompt-injection red-team case
```

Paste analysis example:

```bash
curl -s -X POST http://localhost:8080/api/v1/analyze/paste \
  -H 'Content-Type: application/json' \
  -d '{"format":"whatsapp_export","unknown_caller":true,"text":"[24/08/26, 18:42] Scammer: ApnaBank fraud department se bol raha hoon, OTP code batao turant"}'
```

## Tests and evaluation

```bash
.venv/bin/python -m pytest tests/test_scoring.py tests/test_caller_id.py -q
.venv/bin/python scripts/eval.py --rules-only
```

The verified local run completed 30 unit tests successfully. The dashboard production build also completed successfully. Full provider evaluation depends on the provider keys and model services available in the environment.

## Repository map

| Path | Purpose |
| --- | --- |
| `services/realtime-gateway/` | FastAPI REST/WebSocket gateway and session state |
| `services/scoring/` | Deterministic score, rules, caller ID, and taxonomy |
| `services/ml/` | Local classifier, training, and data generation |
| `services/ai/` | Local/cloud model provider orchestration |
| `services/stt/` | Lazy-loaded faster-whisper voice transcription |
| `services/demo-bank/` | Fictional bank safe-action service |
| `apps/web/dashboard/` | React mission-control dashboard |
| `apps/android/` | Kotlin/Compose mobile client |
| `data/models/` | Bundled trained taxonomy artifact and report |
| `data/scripted-scenarios/` | Reproducible demo conversations |
| `tests/` | Unit tests and golden-set fixtures |
| `docs/` | Assumptions and setup details |
| `demo/` | Presentation screenshots and feature-by-feature explanation |
| `artifacts/RCHAT.apk` | Installable Android debug artifact |

## Privacy and safety boundaries

This is a hackathon prototype, not a production banking security product. It uses fictional bank data and demo accounts. It should not be connected to real customer data without security review, threat modeling, key management, consent design, monitoring, and a production-grade persistence layer.

The intended demo boundaries are:

- User-owned or user-triggered sessions only.
- Persistent analysis indication in the client experience.
- No raw audio persistence in the prototype pipeline.
- Provider keys kept server-side.
- Evidence and scoring designed to be inspectable.
- Safe actions clearly labeled as demo actions where they are not connected to a real bank.

## License and contribution

This repository is a hackathon submission and prototype. Add the project license, team details, and contribution policy that your organization requires before public distribution.
