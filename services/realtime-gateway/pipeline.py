"""Analysis pipeline — fuse Tier-1 rules + trained ML tier + Tier-2 LLM signals.

Used by the paste endpoint, live chat scoring and voice-path scoring alike
(Bible Sections 6-8). The deterministic scorer is the ONLY score producer.

Signal sources and their trust ceiling:
  Tier 1  — regex rules engine       (cap 24,  < 1 ms)
  Tier 15 — trained ML classifier     (cap 74,  ~0.25 ms)
  Tier 2  — streaming LLM providers    (cap 100, 2-20 s)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

from ai.tier2 import (
    ProviderRegistry,
    Tier2CallResult,
    build_user_prompt,
    race_providers,
)
from parsing import ParsedMessage
from scoring.engine import (
    ScoringContext,
    ScoringCounterSignal,
    ScoringSignal,
    score_conversation,
)
from scoring.caller_id import analyze_caller
from scoring.rules_engine import run_counter_rules, run_tier1_message
from scoring.taxonomy import SAFE_ACTIONS_BY_BAND


PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "cloud")  # local | cloud

# ---- adaptive local-model gate (Bible Section 8.4 auto-switch, generalized) ----
# After 2 consecutive local cycles slower than 6 s, stop calling the local model
# for LOCAL_COOLDOWN_S so live 2–4 s cycles stay on the fast provider.
_LOCAL_SLOW_STREAK = {"count": 0}
_LOCAL_DISABLED_UNTIL = [0.0]
LOCAL_COOLDOWN_S = 600.0


def note_local_latency(latency_ms: int) -> None:
    if latency_ms > 8000:
        # blew even the reduced live-path ceiling once -> cool down immediately
        _LOCAL_DISABLED_UNTIL[0] = time.time() + LOCAL_COOLDOWN_S
        _LOCAL_SLOW_STREAK["count"] = 0
        print("[pipeline] local model missed live deadline — cooling down "
              f"{int(LOCAL_COOLDOWN_S)}s")
    elif latency_ms > 6000:
        _LOCAL_SLOW_STREAK["count"] += 1
        if _LOCAL_SLOW_STREAK["count"] >= 2:
            _LOCAL_DISABLED_UNTIL[0] = time.time() + LOCAL_COOLDOWN_S
            print("[pipeline] local model repeatedly slow — cooling down "
                  f"{int(LOCAL_COOLDOWN_S)}s")
    else:
        _LOCAL_SLOW_STREAK["count"] = 0


def local_gate_open() -> bool:
    return time.time() >= _LOCAL_DISABLED_UNTIL[0]


@dataclass
class AnalysisResult:
    score: float
    band: str
    signals: list[dict]
    stage: Optional[str]
    safe_actions: list[str]
    model_results: list[Tier2CallResult]
    tier1_count: int = 0
    ml_count: int = 0
    primary_model_used: str = "none"
    caller_id_warnings: list[str] = field(default_factory=list)


def _window(messages: list[ParsedMessage], last_n: int = 20) -> list[ParsedMessage]:
    return messages[-last_n:]


def _conversation_text(messages: list[ParsedMessage]) -> str:
    return "\n".join(m.text for m in messages)


async def analyze_messages(
    messages: list[ParsedMessage],
    registry: Optional[ProviderRegistry] = None,
    unknown_caller: bool = False,
    cross_channel_otp: bool = False,
    previous_score: Optional[float] = None,
    include_local: bool = True,
    force_models: bool = True,
    local_timeout_s: float | None = None,
    use_ml: bool = True,
    caller_number: Optional[str] = None,
    use_llm: bool = True,
    live_budget_s: float | None = None,
) -> AnalysisResult:
    """Full multi-tier analysis of an ordered conversation.

    force_models=False skips Tier-2 when no provider is usable (rules-only mode).
    use_ml=False skips the trained classifier (e.g. --rules-only eval runs).
    caller_number runs the caller-ID verification tier against bank_directory.json.
    use_llm=False runs the FAST path only (Tier-1 + ML + caller-ID, < 100 ms) —
    used by the live voice loop so alerts fire before the cloud LLM answers.
    """
    tier1_hits: list[ScoringSignal] = []
    counter_hits: list[ScoringSignal] = []
    for i, m in enumerate(messages):
        tier1_hits.extend(run_tier1_message(m.text, message_index=i))
        counter_hits.extend(run_counter_rules(m.text, message_index=i))

    # ---- caller-ID verification tier (deterministic, directory-backed) ----
    caller_id_signals: list[ScoringSignal] = []
    caller_id_counters: list[ScoringCounterSignal] = []
    caller_id_warnings: list[str] = []
    if caller_number:
        try:
            caller_id_signals, caller_id_counters, caller_id_warnings = analyze_caller(
                _conversation_text(messages), caller_number
            )
        except Exception as exc:  # noqa: BLE001 — directory issues must never crash scoring
            print(f"[pipeline] caller-ID tier skipped: {exc}")

    # ---- trained ML tier (tier=15, ~0.25 ms/utterance) ----
    ml_hits: list[ScoringSignal] = []
    ml_counter_hits: list[ScoringCounterSignal] = []
    if use_ml:
        try:
            from ml.classifier import signals_for_messages, available as ml_available

            if ml_available():
                texts = [m.text for m in messages]
                ml_positives, ml_counters = signals_for_messages(texts)
                for sig in ml_positives:
                    ml_hits.append(ScoringSignal(
                        type=sig.type, severity=sig.severity,
                        confidence=sig.confidence, tier=15,
                        message_index=sig.message_index,
                    ))
                for csig in ml_counters:
                    ml_counter_hits.append(ScoringCounterSignal(
                        type=csig.type, confidence=csig.confidence,
                    ))
        except Exception as exc:  # noqa: BLE001 — ML failure must never crash scoring
            print(f"[pipeline] ML tier skipped: {exc}")

    model_results: list[Tier2CallResult] = []
    window = _window(messages)
    conv_text = _conversation_text(window)

    use_local = include_local and local_gate_open()
    if use_llm and registry is not None and (force_models or registry.has_cloud()):
        prompt_msgs = [
            {"message_id": m.message_id, "speaker": m.speaker, "text": m.text}
            for m in window
        ]
        model_results = await race_providers(
            registry, build_user_prompt(prompt_msgs), conv_text,
            include_local=use_local, local_timeout_s=local_timeout_s,
            overall_timeout_s=live_budget_s,
        )
        for res in model_results:
            if res.provider == "ollama":
                note_local_latency(res.latency_ms)

    # ---- merge signals from every successful Tier-2 result + all Tier-1/ML hits
    #    Tier-2 LLM signals are capped per conversation to prevent over-reporting
    #    from inflating scores (the LLM often returns 6-8 labels for a clear scam,
    #    but 2-3 strong signals are enough for the deterministic scorer).
    _MAX_TIER2_SIGNALS = 3
    llm_signals: list[ScoringSignal] = []
    llm_counters: list[ScoringCounterSignal] = []
    stage: Optional[str] = None

    primary = None
    if registry is not None and PRIMARY_MODEL == "cloud":
        primary = registry.primary_cloud()
    elif registry is not None and PRIMARY_MODEL == "local":
        from ai.tier2 import _local_provider_config

        local = _local_provider_config()
        primary = next((r for r in [local] if r), None)

    ordered = sorted(
        model_results,
        key=lambda r: (
            0 if (primary and r.provider == primary.name) else 1,
            r.provider != (primary.name if primary else ""),
        ),
    )
    for res in ordered:
        if not res.ok:
            continue
        for s in res.signals:
            idx = _resolve_message_index(s, messages)
            llm_signals.append(ScoringSignal(
                type=s["type"], severity=s["severity"], confidence=s["confidence"],
                tier=2, message_index=idx,
            ))
        for c in res.counter_signals:
            llm_counters.append(ScoringCounterSignal(type=c["type"], confidence=c["confidence"]))
        if stage is None and res.stage:
            stage = res.stage
        if primary and res.provider == primary.name:
            break  # PRIMARY result drives the live banner; others logged only

    # ---- cap Tier-2 signals per conversation (keep strongest, dedup by label) ----
    if llm_signals:
        llm_signals.sort(key=lambda s: s.confidence, reverse=True)
        seen_labels: set[str] = set()
        kept: list[ScoringSignal] = []
        for sig in llm_signals:
            if sig.type in seen_labels:
                continue  # keep only the strongest instance per label
            seen_labels.add(sig.type)
            kept.append(sig)
            if len(kept) >= _MAX_TIER2_SIGNALS:
                break
        llm_signals = kept

    # ---- deterministic fusion (the ONLY score producer)
    context = ScoringContext(unknown_caller=unknown_caller, cross_channel_otp=cross_channel_otp)
    all_signals = tier1_hits + ml_hits + llm_signals + caller_id_signals
    all_counters = list(counter_hits) + ml_counter_hits + llm_counters + caller_id_counters
    result = score_conversation(
        signals=all_signals,
        counters=all_counters,
        context=context,
        previous_displayed_score=previous_score,
    )

    signal_cards = _signal_cards(result.contributions, tier1_hits + ml_hits, llm_signals, messages)
    band = result.band

    used_model = "none"
    if ordered and ordered[0].ok:
        used_model = ordered[0].model
    elif ml_hits:
        used_model = "tier15_ml"
    elif tier1_hits:
        used_model = "tier1_rules_only"

    return AnalysisResult(
        score=result.score,
        band=band,
        signals=signal_cards,
        stage=stage,
        safe_actions=list(SAFE_ACTIONS_BY_BAND.get(band, [])),
        model_results=model_results,
        tier1_count=len(tier1_hits),
        ml_count=len(ml_hits),
        primary_model_used=used_model,
        caller_id_warnings=caller_id_warnings,
    )


def _resolve_message_index(s: dict, messages: list[ParsedMessage]) -> Optional[int]:
    """Map a Tier-2 evidence quote back to a message index via exact substring match."""
    quote = ((s.get("evidence") or {}).get("quote") or "").strip()
    if not quote:
        ids = (s.get("evidence") or {}).get("message_ids") or []
        for mid in ids:
            try:
                n = int(str(mid).lstrip("m_"))
                return min(max(n - 1, 0), len(messages) - 1)
            except ValueError:
                continue
        return None
    for i, m in enumerate(messages):
        if quote in m.text:
            return i
    normalized = " ".join(quote.split())
    for i, m in enumerate(messages):
        if normalized in " ".join(m.text.split()):
            return i
    return None


def _signal_cards(contributions, tier1_hits, llm_signals, messages) -> list[dict]:
    cards: list[dict] = []
    for c in contributions:
        quote = ""
        msg_id = ""
        for h in tier1_hits + llm_signals:
            if h.type == c.label:
                idx = h.message_index if h.message_index is not None else -1
                if 0 <= idx < len(messages):
                    quote = messages[idx].text[:160]
                    msg_id = messages[idx].message_id
                break
        cards.append({
            "type": c.label,
            "family": c.family,
            "severity_norm": round(c.severity_norm, 3),
            "confidence": round(c.confidence, 3),
            "instances": c.instances,
            "contribution": round(c.contribution, 2),
            "tier": c.tier,
            "evidence": {"message_ids": [msg_id] if msg_id else [], "quote": quote},
        })
    return cards
