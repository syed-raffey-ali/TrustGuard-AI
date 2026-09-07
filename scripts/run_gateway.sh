#!/usr/bin/env bash
# Start the TrustGuard gateway (repo root). Usage: bash scripts/run_gateway.sh
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="services:services/realtime-gateway"
# Live STT tuning: sub-second transcription cadence, smallest fast model.
# 'tiny' transcribes a 2.5 s window in ~1.1–1.9 s on the i5-4200U (base took
# ~4.7 s — slower than real-time, so captions snowballed 17 s behind).
export STT_INTERVAL_S="${STT_INTERVAL_S:-0.5}"
export STT_MODEL="${STT_MODEL:-tiny}"
export STT_COMPUTE_TYPE="${STT_COMPUTE_TYPE:-int8}"
# Live scam-alert latency budget: Tier-2 must answer fast or be cut off
# (Tier-1 + ML fire instantly regardless); local model gets 3 s max.
export LIVE_TIER2_BUDGET_S="${LIVE_TIER2_BUDGET_S:-2.2}"
export LIVE_LOCAL_TIMEOUT_S="${LIVE_LOCAL_TIMEOUT_S:-3}"
# -m uvicorn (not the wrapper script) so the CURRENT venv's interpreter is
# used even after the project folder is moved/renamed.
exec .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080
