# Assumptions & Deviations — TrustGuard AI prototype

Every inference the builders made while implementing the Build Bible v2.0 lives
here (Bible rule: "If anything is ambiguous, state the assumption and proceed").
Bible quotes are abbreviated; nothing here replaces a Bible-defined constant.

## Scoring engine (Section 15)

1. **Modifier order.** The Bible lists caps/floors before the final score line but
   does not pin where `context_floor` sits relative to `uncertainty`. We derived the
   only ordering consistent with all three worked examples:
   `raw → tier1_cap(24) → ±modifiers − uncertainty → clamp 0..100 → context_floor(25) → ratchet`.
   Proof: Example 3 expects exactly 25 after floor; applying the floor before the
   uncertainty penalty yields ~20.8, contradicting "→ Medium ✓".
2. **Frequency bonus grouping.** "freq_i = base_i × 0.08 × (count_i − 1)" is per-label.
   We take each label's strongest instance (max confidence) as its base; repeats of the
   same label add up to +30 % of *that* base. Alternative readings stack whole bases per
   instance, which would let repetition alone reach Critical — against the Bible's
   anti-inflation spirit ("Critical requires corroboration, never one keyword").
3. **Corroboration is strictly A∧B.** "≥2 distinct families (A and B)" is implemented
   as: at least one Family-A signal AND one Family-B signal, each with confidence ≥0.80.
   A+B+C or B+C combinations do not qualify.
4. **Chronology window.** Text channel: |message_index difference| ≤ 3 between a
   Family-B and a Family-A signal. Voice channel: |position difference| ≤ 120 s.
   Signals lacking any position are not counted for chronology.
5. **Counter-signal cap** applies to the sum of Family-D contributions per cycle
   (max(Σ, −15)), matching "a scammer cannot talk the score to zero".
6. **Ratchet** operates on the displayed score across cycles: `displayed = max(score,
   previous − 5)`. Rises are never limited. Persisted in session state; paste analyses
   have no history (no ratchet) unless chained by the caller.
7. **Score display**: internal float rounded to 1–2 decimals for display; band computed
   from the un-rounded value with boundaries Low ≤24, Medium 25–49, High 50–74,
   Critical ≥75.

## Tier-2 LLM client (Sections 8–9)

8. **Provider generalization.** The Bible's dual-model race (local Ollama vs cloud
   Alibaba qwen-plus) is preserved verbatim as two participants in a generalized
   OpenAI-compatible provider registry. Built-ins: alibaba (priority 5), groq (10),
   gemini (20), openrouter (30); plus unlimited custom providers added at runtime via
   `POST /api/v1/admin/providers` (persisted to `data/providers.json`). The user
   explicitly requested multi-provider support to benchmark several free clouds.
9. **PRIMARY selection.** `PRIMARY_MODEL=cloud` uses the lowest-priority-number cloud
   provider that has an API key; `PRIMARY_CLOUD_PROVIDER` env can force one by name.
   In every cycle ALL usable providers race concurrently (`asyncio.gather`), results are
   logged to `model_comparisons`, and the primary's signals drive the live banner while
   others are recorded for the Model Race panel.
10. **JSON mode fallback.** Cloud calls request `response_format: {"type":"json_object"}`;
    if a provider rejects it we retry once without JSON mode, then one repair retry with
    the parse error appended (Bible 8.3). Still-invalid output counts toward the
    parse-failure-rate metric and never crashes the pipeline — rules-only scoring continues.
11. **Local-model latency gate.** Bible 8.4 mandates auto-switch when local exceeds 6 s
    twice consecutively. Implemented additionally as a hard cooldown: a single local call
    missing the reduced live ceiling (8 s, `LIVE_LOCAL_TIMEOUT_S`) disables the local
    model for 10 minutes on live paths so the 2–4 s cycle budget survives on slow CPUs.
    Paste/batch analysis allows up to `LOCAL_TIMEOUT_S` (default 25 s). On the demo laptop
    (2-core i5-4200U CPU, no GPU) qwen2.5:3b-instruct generates at ~1–2 tokens/s ≈ 30 s+
    per response — measured honestly and reported in the metrics bar; cloud is therefore
    PRIMARY for the demo, local remains the offline/privacy fallback exactly as pitched.
12. **Evidence verification.** Every LLM signal carries `evidence.quote`; the validator
    checks the quote is an exact substring (whitespace-normalized fallback) of the
    conversation and flags `verified_substring`. Unverifiable evidence keeps the signal
    but lowers trust on the dashboard card.

## Gateway / pipeline

13. **Single deployable gateway.** Appendix D shows services as folders; we keep the
    layout but ship ONE FastAPI process (`services/realtime-gateway`) importing
    `scoring`, `ai`, `stt` packages via PYTHONPATH, because the folder name
    `realtime-gateway` cannot be a Python package (hyphen). Run pattern:
    `PYTHONPATH=services:services/realtime-gateway uvicorn main:app --port 8080`.
    Port is 8080 (not 8000): port 8000 was already occupied on the build machine.
14. **DB fallback.** PostgreSQL+Redis via docker compose is the reference deployment.
    When unreachable, SQLAlchemy falls back to SQLite (`data/trustguard.db`) and WS
    fan-out runs purely in-memory — documented so laptop development never blocks.
15. **WS audio protocol** (Section 14 asked us to pick one): binary frames = raw PCM16
    16 kHz mono audio chunks (~100 ms); control messages = JSON TEXT frames
    (`{"type":"control","event":"start|end",...}`, transcripts arrive back from STT as
    `{"type":"transcript_segment",...}`). One text frame registers a peer before binary
    runs begin.
16. **Cross-channel linking (Phase 2.5).** An OTP-format message on the chat channel arms
    the +10 modifier on any ACTIVE call session sharing device ids, or explicitly linked
    via `POST /api/v1/sessions/{chat_id}/link_call/{call_id}` (used by Scenario B replay
    for determinism). Evidence card is pushed on the risk channel.
17. **Paste speaker roles.** Pasted conversations keep original sender names; roles are
    not guessed into "victim/scammer" — the analyzer judges the conversation shape
    regardless of side, matching how judges will paste real SMS they received.
18. **Date-order ambiguity.** WhatsApp exports may be DD/MM (Android) or MM/DD (iOS).
    Auto-detection: a component >12 must be the day; ambiguous cases default DD/MM and
    set a flag. Timestamps only affect chronology windows, not scoring math.
19. **Tier-1 dedupe.** One instance per label per message (overlapping regexes don't
    inflate frequency bonuses); repeats ACROSS messages legitimately count.

## Content & compliance

20. **Fictional banks only**: ApnaBank, Metro Commercial Bank (plus generic wallet names
    that Appendix A itself lists as impersonation targets). No real bank appears in any
    scam script, golden-set item, or dashboard copy.
21. **Golden set authorship.** The 60 conversations were authored directly by the build
    agent (an earlier delegation attempt silently produced nothing — see git-less dev log);
    distribution validated by `scripts/seed_golden_set.py` (35/20/5, ≥40 % Roman-Urdu-like —
    actual 81 %, ≥1 per Family-A pattern, ≥5 bank/OTP, ≥5 adversarial-benign, 5 injections).
22. **Eval targets need a working Tier-2.** Rules-only eval scores precision 1.000 but
    recall ≈0.63 because the Bible's own cap forbids Tier-1-only exceeding Medium. Full
    targets (recall ≥0.90 etc.) are reachable only with a configured cloud/local Tier-2 —
    this is the intended architecture, not a defect. `eval_results.json` records which
    models participated per conversation.
23. **Android clips.** Director voice mode references pre-recorded `.wav` files under
    `assets/director/clips/` (Bible Section 5 rejects TTS-to-mic loopback). Clips are
    recorded once by the team; file naming contract documented in the assets README.
24. **Dashboard tolerance.** Payload types are parsed tolerantly (optional fields,
    fraction-or-percent heuristics) so a partially-configured backend never blanks the UI.
