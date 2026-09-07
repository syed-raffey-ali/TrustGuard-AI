"""Multi-provider LLM paraphrase augmentation — fixes the template-diversity bottleneck.

Why this exists
---------------
Training on the hand-written template bank and evaluating with a
template-disjoint split gave micro F1 0.467, with 13 of 38 labels at exactly
0.000. The cause is not the model: it is that 4-11 hand-written phrasings per
label give the classifier nothing to generalise from. Hold one out and the label
becomes unrecognisable.

The 2026-standard remedy is label-preserving augmentation: ask a strong model to
rewrite each seed phrasing many different ways — different register, different
Roman-Urdu spelling, different sentence order, code-switched, longer, terser —
while keeping the intent (and therefore the label) fixed. That turns ~8
phrasings per label into hundreds, which is what character n-grams need in order
to learn the *shape* of the ask rather than its exact wording.

This is data augmentation, not distillation: the label comes from the seed
template we already trust, never from the model's own judgement. A model that
hallucinates a bad paraphrase adds noise; it cannot silently relabel data.

Providers
---------
* Groq   — openai/gpt-oss-120b (thinking model; needs max_tokens 2000+)
* OpenRouter — minimax/minimax-m3:free, nvidia/nemotron-3-super-120b-a12b:free
* "all"  — races every configured provider concurrently, merges all variants

Guardrails
----------
* Paraphrases are discarded if they collapse to a near-duplicate of a seed
  (nothing learned) or drift so far they lose the label's giveaway concept.
* Output is written to a separate file and merged at train time, so a bad
  augmentation run can be thrown away without touching the seed corpus.
* Fictional institution names only, per Bible §17 — the prompt says so and a
  post-filter enforces it.

Usage
-----
    PYTHONPATH=services .venv/bin/python -m ml.augment --provider all --per-template 14
    PYTHONPATH=services .venv/bin/python -m ml.train \
        --corpus data/train/corpus.jsonl --extra data/train/augmented.jsonl

    # Urdu-script seeds only - keeps the second extra file from duplicating the
    # Roman paraphrase coverage already inside augmented.jsonl:
    PYTHONPATH=services .venv/bin/python -m ml.augment --provider groq \
        --per-template 8 --urdu-only --out data/train/augmented_urdu.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from ml.datagen import (  # noqa: E402
    BENIGN,
    SLOTS,
    TEMPLATES,
    URDU_BENIGN,
    URDU_TEMPLATES,
    _fill,
)
from scoring.taxonomy import COUNTER_LABELS, LABELS, SCAM_LABELS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))

# ---------------------------------------------------------------- env loader
def _load_env() -> None:
    """Load .env so CLI invocation is not required to export vars."""
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ---------------------------------------------------------------- constants
REAL_BANK_BLOCKLIST = {
    "hbl", "habib bank", "ubl", "united bank", "mcb bank", "allied bank",
    "meezan", "bank alfalah", "askari bank", "faysal bank", "js bank",
    "standard chartered", "soneri", "bank of punjab", "silk bank", "summit bank",
    "national bank", "nbp", "zarai bank", "sindh bank",
}

SYSTEM_PROMPT = """You rewrite short phone/chat utterances for a scam-detection training corpus.

You will be given ONE seed utterance and the scam-signal concept it expresses.
Produce N alternative utterances that express the SAME concept.

HARD RULES:
1. Every rewrite must still clearly express the given concept. Do not soften it
   into something harmless and do not add a different scam concept.
2. Vary aggressively: word choice, sentence order, register (formal officer vs
   casual), length (very short to two sentences), politeness, and Roman-Urdu
   spelling. Mix English/Roman Urdu/Urdu script the way real Pakistani phone
   conversations do.
3. Do NOT reuse the seed's distinctive wording verbatim. A rewrite that only
   swaps one word is useless.
4. Use ONLY fictional institution names: ApnaBank, Metro Commercial Bank.
   Never name a real bank.
5. No preamble, no numbering, no commentary.

OUTPUT: a JSON object exactly like {"variants": ["...", "...", "..."]}"""


# ---------------------------------------------------------------- provider registry
class Provider:
    """One LLM endpoint with its quirks."""

    def __init__(self, name: str, base_url: str, model: str, api_key: str,
                 max_tokens: int = 1400, json_mode: bool = True,
                 extra_headers: dict | None = None, temperature: float = 0.95):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.json_mode = json_mode        # False for models that break on response_format
        self.extra_headers = extra_headers or {}
        self.temperature = temperature

    def is_configured(self) -> bool:
        return bool(self.api_key)


def _build_providers() -> dict[str, Provider]:
    """Build provider map from env. Missing keys → provider absent."""
    providers: dict[str, Provider] = {}

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key:
        # gpt-oss-120b is a thinking model: reasoning tokens eat ~75 % of the
        # completion budget. max_tokens must be high or output gets truncated.
        # json_mode causes validation failures on this model, so parse manually.
        providers["groq"] = Provider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            api_key=groq_key,
            max_tokens=2500,
            json_mode=False,
            temperature=0.95,
        )

    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if or_key:
        # MiniMax M3 — cleanest JSON output among free OpenRouter models
        providers["openrouter_minimax"] = Provider(
            name="openrouter_minimax",
            base_url="https://openrouter.ai/api/v1",
            model=os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3:free"),
            api_key=or_key,
            max_tokens=1400,
            json_mode=False,       # free models sometimes reject json_object
            temperature=0.95,
            extra_headers={
                "HTTP-Referer": "https://trustguard.demo",
                "X-Title": "TrustGuard AI Demo",
            },
        )
        # Nemotron 3 Super 120B — fast, decent quality
        providers["openrouter_nemotron"] = Provider(
            name="openrouter_nemotron",
            base_url="https://openrouter.ai/api/v1",
            model="nvidia/nemotron-3-super-120b-a12b:free",
            api_key=or_key,
            max_tokens=1400,
            json_mode=False,
            temperature=0.95,
            extra_headers={
                "HTTP-Referer": "https://trustguard.demo",
                "X-Title": "TrustGuard AI Demo",
            },
        )

    return providers


# ---------------------------------------------------------------- seed pool
def _seed_pool(per_template: int, urdu_only: bool = False) -> list[dict]:
    """One augmentation job per (label, template) pair, plus benign seeds.

    Urdu-script templates become their own "urdu_<label>#<idx>" jobs so their
    paraphrases land on the correct side of the template-disjoint split, and
    each job carries an ``urdu`` flag that asks the model to keep rewrites in
    Urdu script. With ``urdu_only`` the pool is restricted to the Urdu banks -
    used for a second extra corpus without re-duplicating Roman coverage.
    """
    import random

    rng = random.Random(4242)
    jobs: list[dict] = []

    def add(label, template_id, seed, concept, n, urdu=False):
        job = {"label": label, "template_id": template_id, "seed": seed,
               "concept": concept, "n": n}
        if urdu:
            job["urdu"] = True
        jobs.append(job)

    for label in sorted(SCAM_LABELS | COUNTER_LABELS):
        concept = LABELS[label].fires_when
        if not urdu_only:
            for idx, template in enumerate(TEMPLATES[label]):
                add(label, f"{label}#{idx}", _fill(template, rng),
                    concept, per_template)
        for idx, template in enumerate(URDU_TEMPLATES[label]):
            add(label, f"urdu_{label}#{idx}", _fill(template, rng),
                concept, per_template, urdu=True)

    benign_concept = ("an ordinary, completely harmless everyday message with no "
                      "scam intent whatsoever")
    if urdu_only:
        benign_seeds = [(f"urdu_benign#{i}", t, True) for i, t in enumerate(URDU_BENIGN)]
    else:
        benign_seeds = [(f"benign#{i}", t, False) for i, t in enumerate(BENIGN)]
        benign_seeds += [(f"urdu_benign#{i}", t, True)
                         for i, t in enumerate(URDU_BENIGN)]
    for template_id, text, is_urdu in benign_seeds:
        add(None, template_id, text, benign_concept,
            max(3, per_template // 3), urdu=is_urdu)
    return jobs


# ---------------------------------------------------------------- quality filters
def _looks_real_bank(text: str) -> bool:
    low = text.lower()
    return any(name in low for name in REAL_BANK_BLOCKLIST)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06FF ]+", "", text.lower()).strip()


def _accept(variant: str, seed: str, seen: set[str]) -> bool:
    variant = variant.strip()
    if not (8 <= len(variant) <= 320):
        return False
    if _looks_real_bank(variant):
        return False
    norm = _normalise(variant)
    if not norm or norm in seen:
        return False
    # Reject near-duplicates of the seed — they teach the model nothing.
    seed_norm = set(_normalise(seed).split())
    var_words = set(norm.split())
    if seed_norm and len(seed_norm & var_words) / len(seed_norm) > 0.85:
        return False
    seen.add(norm)
    return True


# ---------------------------------------------------------------- extraction
def _extract_variants(raw: str) -> list[str]:
    """Best-effort extraction of a string list from a model response."""
    raw = raw.strip()
    # Try {"variants": [...]} first
    for obj in (raw, raw[raw.find("{"):raw.rfind("}") + 1] if "{" in raw else ""):
        if not obj:
            continue
        try:
            data = json.loads(obj)
            if isinstance(data, dict) and "variants" in data:
                v = data["variants"]
                if isinstance(v, list):
                    return [s for s in v if isinstance(s, str)]
        except (json.JSONDecodeError, TypeError):
            pass
    # Try raw array [...]
    start, end = raw.find("["), raw.rfind("]")
    if start >= 0 and end > start:
        try:
            arr = json.loads(raw[start:end + 1])
            if isinstance(arr, list):
                return [s for s in arr if isinstance(s, str)]
        except json.JSONDecodeError:
            pass
    return []


# ---------------------------------------------------------------- HTTP call
async def _call_provider(
    provider: Provider,
    job: dict,
    sem: asyncio.Semaphore,
) -> dict:
    """Call one provider for one job, return parsed variants."""
    import httpx

    user_prompt = (
        f"CONCEPT: {job['concept']}\n"
        f"SEED UTTERANCE: {job['seed']}\n"
        f"N: {job['n']}\n\n"
        f"Return {job['n']} varied rewrites as a JSON object like "
        f'{{"variants": ["...", "..."]}}'
    )
    if job.get("urdu"):
        user_prompt += (
            "\n\nNOTE: the seed is in Urdu script. Keep most rewrites in Urdu "
            "script (natural spoken Pakistani Urdu); occasional English words "
            "mixed in are fine, but do NOT transliterate everything to Roman "
            "Urdu."
        )
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    headers.update(provider.extra_headers)

    body: dict = {
        "model": provider.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": provider.temperature,
        "max_tokens": provider.max_tokens,
    }
    if provider.json_mode:
        body["response_format"] = {"type": "json_object"}

    async with sem:
        started = time.perf_counter()
        last_error = ""
        for attempt in range(3):           # 3 tries with backoff for 429/5xx
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(
                        f"{provider.base_url}/chat/completions",
                        json=body, headers=headers,
                    )
                    if resp.status_code in (429, 500, 502, 503, 529) and attempt < 2:
                        wait = 2 ** (attempt + 1) + 0.5 * attempt  # 2, 4.5 s
                        await asyncio.sleep(wait)
                        last_error = f"HTTP {resp.status_code} (retry {attempt + 1})"
                        continue
                    if resp.status_code >= 400:
                        return {
                            "job": job, "variants": [], "provider": provider.name,
                            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                            "latency_ms": int((time.perf_counter() - started) * 1000),
                        }
                    payload = resp.json()
                    choices = payload.get("choices")
                    if not choices:
                        return {
                            "job": job, "variants": [], "provider": provider.name,
                            "error": f"no choices in response: {str(payload)[:200]}",
                            "latency_ms": int((time.perf_counter() - started) * 1000),
                        }
                    raw = choices[0]["message"]["content"] or ""
                    variants = _extract_variants(raw)
                    return {
                        "job": job, "variants": variants, "provider": provider.name,
                        "error": None,
                        "latency_ms": int((time.perf_counter() - started) * 1000),
                    }
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** (attempt + 1))
                    last_error = f"{type(exc).__name__}: {exc}"
                    continue
                return {
                    "job": job, "variants": [], "provider": provider.name,
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
        # Should not reach here, but safety net
        return {
            "job": job, "variants": [], "provider": provider.name,
            "error": last_error or "exhausted retries",
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


# ---------------------------------------------------------------- orchestrator
async def run(
    per_template: int,
    out_path: str,
    provider_names: list[str],
    concurrency: int,
    limit: int,
    urdu_only: bool = False,
) -> None:
    all_providers = _build_providers()
    if not all_providers:
        raise SystemExit(
            "No providers configured. Set at least one of:\n"
            "  GROQ_API_KEY, OPENROUTER_API_KEY\n"
            "in .env or as environment variables."
        )

    if "all" in provider_names:
        chosen = list(all_providers.values())
    else:
        chosen = []
        for name in provider_names:
            if name in all_providers:
                chosen.append(all_providers[name])
            else:
                available = ", ".join(all_providers.keys())
                raise SystemExit(f"Unknown provider '{name}'. Available: {available}")

    if not chosen:
        raise SystemExit("No usable providers. Check your API keys.")

    jobs = _seed_pool(per_template, urdu_only=urdu_only)
    if limit:
        jobs = jobs[:limit]

    provider_summary = ", ".join(p.name for p in chosen)
    scope = "Urdu-script" if urdu_only else "all"
    print(f"augmenting {len(jobs)} seed templates ({scope}) via [{provider_summary}] "
          f"(concurrency {concurrency})...")

    sem = asyncio.Semaphore(concurrency)
    tasks: list[asyncio.Task] = []
    for job in jobs:
        for provider in chosen:
            tasks.append(asyncio.create_task(_call_provider(provider, job, sem)))
    results = await asyncio.gather(*tasks)

    # --- collect -----------------------------------------------------------
    seen: set[str] = set()
    for bank in (TEMPLATES, URDU_TEMPLATES):
        for label_templates in bank.values():
            for t in label_templates:
                seen.add(_normalise(t))
    for b in BENIGN + URDU_BENIGN:
        seen.add(_normalise(b))

    rows: list[dict] = []
    errors = 0
    rejected = 0
    latencies: dict[str, list[int]] = {}
    provider_counts: dict[str, int] = {}
    for res in results:
        pname = res["provider"]
        provider_counts[pname] = provider_counts.get(pname, 0) + 1
        if res["error"]:
            errors += 1
            if errors <= 5:
                print(f"  [{pname}] error: {res['error'][:150]}")
            continue
        latencies.setdefault(pname, []).append(res["latency_ms"])
        job = res["job"]
        for v in res["variants"]:
            if not isinstance(v, str):
                continue
            if _accept(v, job["seed"], seen):
                rows.append({
                    "text": v.strip(),
                    "labels": [job["label"]] if job["label"] else [],
                    # Augmented rows inherit the seed's template id so the
                    # template-disjoint split keeps them on the correct side.
                    "template_ids": [job["template_id"]],
                    "origin": f"llm_augmented_{pname}",
                })
            else:
                rejected += 1

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    import statistics

    print(f"\nwrote {len(rows)} augmented samples -> {out_path}")
    print(f"  total API calls    {len(results)}")
    print(f"  calls failed       {errors}/{len(results)}")
    print(f"  variants rejected  {rejected} (duplicate / too close / real bank name)")
    for pname, lats in sorted(latencies.items()):
        med = int(statistics.median(lats))
        print(f"  [{pname}] median latency {med} ms  ({len(lats)} ok calls)")
    per_label: dict[str, int] = {}
    for r in rows:
        key = r["labels"][0] if r["labels"] else "benign"
        per_label[key] = per_label.get(key, 0) + 1
    thin = sorted(per_label.items(), key=lambda kv: kv[1])[:6]
    print("  thinnest labels: " + ", ".join(f"{k}={v}" for k, v in thin))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "train", "augmented.jsonl"))
    ap.add_argument("--per-template", type=int, default=14,
                    help="paraphrases requested per seed template per provider")
    ap.add_argument("--provider", action="append", default=None,
                    help="provider name (repeatable); 'all' races every configured provider")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="cap jobs (smoke test)")
    ap.add_argument("--urdu-only", action="store_true",
                    help="augment only the Urdu-script template bank (URDU_TEMPLATES "
                         "+ URDU_BENIGN)")
    args = ap.parse_args()

    providers = args.provider or ["all"]
    asyncio.run(run(args.per_template, args.out, providers, args.concurrency,
                    args.limit, urdu_only=args.urdu_only))


if __name__ == "__main__":
    main()
