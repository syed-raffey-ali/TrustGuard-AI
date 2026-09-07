#!/usr/bin/env python3
"""Golden-set evaluation — Build Bible Section 16.

Runs every labelled conversation in tests/golden_set/ through the FULL pipeline
(Tier-1 rules + every configured Tier-2 provider + deterministic scorer), then
prints precision/recall/F1/band-correct/latency and writes eval_results.json.

Usage (repo root):
    .venv/bin/python scripts/eval.py                 # full pipeline
    .venv/bin/python scripts/eval.py --rules-only   # Tier-1 only sanity mode
    .venv/bin/python scripts/eval.py --limit 10     # quick subset

Targets: precision >= 0.85, recall >= 0.90, band-correct(±1) >= 0.80,
100% injection conversations still flagged, median Tier-2 latency <= 4 s.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env before any service imports so tier2.py picks up API keys
def _load_env() -> None:
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

sys.path.insert(0, os.path.join(ROOT, "services"))
sys.path.insert(0, os.path.join(ROOT, "services", "realtime-gateway"))

from parsing import ParsedMessage  # noqa: E402

BAND_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def load_conversations(directory: str) -> list[dict]:
    convos = []
    for path in sorted(glob.glob(os.path.join(directory, "gs_*.json"))):
        with open(path) as fh:
            convos.append(json.load(fh))
    return convos


def to_messages(conv: dict) -> list[ParsedMessage]:
    return [
        ParsedMessage(
            message_id=m.get("message_id") or f"m_{i + 1}",
            speaker=m.get("speaker", "them"),
            text=m.get("text", ""),
            timestamp=str(m.get("timestamp_offset_s", 0)),
        )
        for i, m in enumerate(conv["messages"])
    ]


async def evaluate(convs: list[dict], rules_only: bool, unknown_caller_default: bool,
                   use_ml: bool = True) -> dict:
    from ai.tier2 import ProviderRegistry
    from pipeline import analyze_messages

    registry = ProviderRegistry()
    rows = []
    latencies: dict[str, list[int]] = {"local": [], "cloud": []}

    for i, conv in enumerate(convs):
        started = time.perf_counter()
        analysis = await analyze_messages(
            to_messages(conv),
            registry,
            unknown_caller=unknown_caller_default,
            include_local=True,
            force_models=not rules_only,
            use_ml=use_ml and not rules_only,
        )
        wall_ms = int((time.perf_counter() - started) * 1000)
        for res in analysis.model_results:
            bucket = "local" if res.provider == "ollama" else "cloud"
            if res.ok:
                latencies[bucket].append(res.latency_ms)

        expected_flagged = conv["label"] in ("scam", "injection")
        # Flagged means the system would at least show a yellow indicator.
        flagged = analysis.score >= 25
        band_ok = abs(BAND_ORDER[analysis.band] - BAND_ORDER[conv["expected_band"]]) <= 1
        rows.append({
            "id": conv["id"],
            "label": conv["label"],
            "family": conv.get("family"),
            "language": conv.get("language"),
            "expected_band": conv["expected_band"],
            "score": round(analysis.score, 1),
            "band": analysis.band,
            "flagged": flagged,
            "expected_flagged": expected_flagged,
            "band_ok": band_ok,
            "models_used": [r.provider for r in analysis.model_results if r.ok],
            "wall_ms": wall_ms,
        })
        marker = "✓" if (flagged == expected_flagged and band_ok) else "✗"
        ml_tag = f" ml={analysis.ml_count}" if analysis.ml_count else ""
        print(f"[{i + 1:>2}/{len(convs)}] {marker} {conv['id']} {conv['label']:<9}"
              f" exp={conv['expected_band']:<8} got={analysis.band:<8} "
              f"score={analysis.score:<6}{ml_tag} models={rows[-1]['models_used']}")

    return summarize(rows, latencies)


def summarize(rows: list[dict], latencies: dict[str, list[int]]) -> dict:
    tp = sum(1 for r in rows if r["expected_flagged"] and r["flagged"])
    fp = sum(1 for r in rows if not r["expected_flagged"] and r["flagged"])
    fn = sum(1 for r in rows if r["expected_flagged"] and not r["flagged"])
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    band_correct = sum(1 for r in rows if r["band_ok"]) / len(rows) if rows else 0.0
    inj_rows = [r for r in rows if r["label"] == "injection"]
    injection_pass = (all(r["flagged"] for r in inj_rows) and len(inj_rows) > 0) if inj_rows else None

    def median(vals):
        return int(statistics.median(vals)) if vals else None

    result = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conversations": len(rows),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "band_correct": round(band_correct, 4),
        "band_flip_rate": round(sum(1 for r in rows if not r["band_ok"]) / len(rows), 4) if rows else 0,
        "injection_pass": injection_pass,
        "median_latency_ms_cloud": median(latencies["cloud"]),
        "median_latency_ms_local": median(latencies["local"]),
        "targets": {
            "precision_min": 0.85,
            "recall_min": 0.90,
            "band_correct_min": 0.80,
            "tier2_median_max_ms": 4000,
            "injection_pass_required": True,
        },
        "passes_targets": (
            precision >= 0.85
            and recall >= 0.90
            and band_correct >= 0.80
            and (injection_pass is True or injection_pass is None)
        ),
        "per_conversation": rows,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden-dir", default=os.path.join(ROOT, "tests", "golden_set"))
    parser.add_argument("--out", default=os.path.join(ROOT, "eval_results.json"))
    parser.add_argument("--rules-only", action="store_true",
                        help="skip Tier-2 LLM calls and ML tier (Tier-1 regex only)")
    parser.add_argument("--no-ml", action="store_true",
                        help="disable the trained ML classifier (keep Tier-1 + Tier-2 LLM)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--unknown-caller", action="store_true", default=True,
                        help="assume unknown callers for context floor (default true)")
    args = parser.parse_args()

    convs = load_conversations(args.golden_dir)
    if not convs:
        print("No conversations found — run scripts/seed_golden_set.py first.")
        sys.exit(2)
    if args.limit:
        # keep label proportions in the subset
        by_label: dict[str, list[dict]] = {}
        for c in convs:
            by_label.setdefault(c["label"], []).append(c)
        n = args.limit
        total = len(convs)
        picked: list[dict] = []
        for label, group in by_label.items():
            k = max(1, round(n * len(group) / total))
            picked.extend(group[:k])
        convs = picked[:n]

    mode_desc = "Tier-1 rules only" if args.rules_only else (
        "Tier-1 + ML + Tier-2 LLM" if not args.no_ml else "Tier-1 + Tier-2 LLM (no ML)"
    )
    print(f"Evaluating {len(convs)} conversations ({mode_desc})...\n")
    result = asyncio.run(evaluate(convs, args.rules_only, args.unknown_caller,
                                  use_ml=not args.no_ml))

    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)

    print("\n================ RESULTS ================")
    print(f"precision          {result['precision']:.3f}   (target ≥ 0.85)")
    print(f"recall             {result['recall']:.3f}   (target ≥ 0.90)")
    print(f"f1                 {result['f1']:.3f}")
    print(f"band-correct (±1)  {result['band_correct']:.3f}   (target ≥ 0.80)")
    print(f"injection pass     {result['injection_pass']}")
    print(f"latency median     cloud={result['median_latency_ms_cloud']}ms local={result['median_latency_ms_local']}ms")
    print(f"PASSES TARGETS     {result['passes_targets']}")
    print(f"\nwritten to {args.out}")
    sys.exit(0 if result["passes_targets"] else 1)


if __name__ == "__main__":
    main()
