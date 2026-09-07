"""Runtime inference for the trained taxonomy tier.

Loaded once per process and reused; a scoring call is a single sparse matrix
multiply, so it costs well under a millisecond per utterance. This is the tier
that keeps live detection inside the Bible's <150 ms budget on hardware where an
LLM needs 23 seconds.

Two threshold profiles
----------------------
balanced   - per-label thresholds tuned for F1 during training.
precision  - thresholds raised toward high confidence. This is the default for
             live scoring, because a false Critical on a real conversation costs
             far more trust than a missed Medium, and the Tier-2 LLM is still
             there to catch what this tier passes over.

Signals emitted here are tagged source="ml" so the deterministic scorer can
apply its own ceiling to them (see scoring.engine): the trained tier can lift a
conversation into High on its own, but reaching Critical still requires
corroboration, exactly as Bible §3 demands.
"""

from __future__ import annotations

import functools
import os
import threading
from dataclasses import dataclass
from typing import Optional

from ml import DEFAULT_MODEL_SUBDIR, MODEL_BASENAME, MODEL_DIR_ENV

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_LOCK = threading.Lock()

# Raise every tuned threshold toward confidence for live use, but never above
# this ceiling or rare labels would become unreachable.
PRECISION_FLOOR = 0.60
PRECISION_CEILING = 0.90


@dataclass
class MLSignal:
    type: str
    confidence: float
    severity: int
    message_index: Optional[int] = None


def model_path() -> str:
    override = os.getenv(MODEL_DIR_ENV)
    base = override if override else os.path.join(_ROOT, DEFAULT_MODEL_SUBDIR)
    return os.path.join(base, f"{MODEL_BASENAME}.joblib")


@functools.lru_cache(maxsize=1)
def _load() -> Optional[dict]:
    """Load the artifact once. Missing model is not an error - the system
    degrades to rules + Tier-2, which is the documented fallback path."""
    path = model_path()
    if not os.path.exists(path):
        print(f"[ml] no trained model at {path} - trained tier disabled "
              f"(run: PYTHONPATH=services python -m ml.train)")
        return None
    try:
        # joblib.load unpickles, which can execute code. Trust boundary: this
        # artifact is produced locally by ml.train from a local corpus and is
        # gitignored - never load a tier15_taxonomy.joblib received from a third
        # party. If artifacts ever get distributed, sign them and verify first.
        import joblib

        bundle = joblib.load(path)
        print(f"[ml] trained tier loaded ({len(bundle['classes'])} labels, "
              f"trained_at={bundle.get('trained_at')})")
        return bundle
    except Exception as exc:  # noqa: BLE001 - never let a bad artifact kill the gateway
        print(f"[ml] failed to load {path}: {type(exc).__name__}: {exc}")
        return None


def available() -> bool:
    return _load() is not None


def model_info() -> dict:
    bundle = _load()
    if not bundle:
        return {"available": False, "path": model_path()}
    return {
        "available": True,
        "path": model_path(),
        "labels": len(bundle["classes"]),
        "trained_at": bundle.get("trained_at"),
    }


def _thresholds(profile: str) -> dict[str, float]:
    bundle = _load()
    if not bundle:
        return {}
    tuned = bundle["thresholds"]
    if profile == "balanced":
        return tuned
    return {
        label: min(PRECISION_CEILING, max(PRECISION_FLOOR, t))
        for label, t in tuned.items()
    }


def _severity_for(label: str, confidence: float) -> int:
    """Derive Bible-compatible severity 1-5 from label weight and confidence.

    The taxonomy weight already encodes how dangerous a label is; severity
    modulates it by how strongly this utterance expressed it. Family-B credential
    theft at high confidence lands at 5, matching the worked examples in §15.5.
    """
    from scoring.taxonomy import LABELS

    weight = abs(LABELS[label].weight)
    if weight >= 24:
        base = 5
    elif weight >= 16:
        base = 4
    elif weight >= 10:
        base = 3
    elif weight >= 8:
        base = 2
    else:
        base = 1
    if confidence < 0.55 and base > 1:
        base -= 1
    return max(1, min(5, base))


def classify(texts: list[str], profile: str = "precision") -> list[dict[str, float]]:
    """Per-utterance label -> confidence, keeping only labels over threshold."""
    bundle = _load()
    if not bundle or not texts:
        return [{} for _ in texts]

    with _LOCK:  # sklearn pipelines are not guaranteed thread-safe for predict
        probs = bundle["pipeline"].predict_proba(texts)

    classes = bundle["classes"]
    thr = _thresholds(profile)
    out: list[dict[str, float]] = []
    for row in probs:
        hits = {
            classes[j]: round(float(p), 4)
            for j, p in enumerate(row)
            if p >= thr.get(classes[j], 0.5)
        }
        out.append(hits)
    return out


def signals_for_messages(
    texts: list[str], profile: str = "precision"
) -> tuple[list[MLSignal], list[MLSignal]]:
    """Split trained-tier hits into positive signals and counter-signals.

    Returns (signals, counter_signals) so the caller can feed them to the
    deterministic scorer without knowing anything about the taxonomy's sign
    convention.
    """
    from scoring.taxonomy import COUNTER_LABELS

    positives: list[MLSignal] = []
    counters: list[MLSignal] = []
    for idx, hits in enumerate(classify(texts, profile=profile)):
        for label, conf in hits.items():
            sig = MLSignal(
                type=label,
                confidence=conf,
                severity=_severity_for(label, conf),
                message_index=idx,
            )
            (counters if label in COUNTER_LABELS else positives).append(sig)
    return positives, counters


def explain(text: str, top_k: int = 6) -> list[tuple[str, float]]:
    """Highest-probability labels regardless of threshold - for the dashboard
    and for debugging why a conversation did or did not fire."""
    bundle = _load()
    if not bundle:
        return []
    with _LOCK:
        row = bundle["pipeline"].predict_proba([text])[0]
    ranked = sorted(
        ((bundle["classes"][j], float(p)) for j, p in enumerate(row)),
        key=lambda kv: -kv[1],
    )
    return [(name, round(p, 4)) for name, p in ranked[:top_k]]
