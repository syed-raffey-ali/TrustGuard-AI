"""TrustGuard trained-model tier.

This package adds the piece the Build Bible deferred (§8.5 "no fine-tuning
required"): a real trained multi-label classifier over the Appendix-A taxonomy.

Why it exists
-------------
Tier-1 regex only fires on phrasings someone wrote down in advance. A scammer
who says "wo chhe ainkon wala number jo msg aya hai wo sunaein" instead of
"OTP batao" walks straight past it. The trained tier generalises over
character n-grams, so Roman-Urdu spelling drift, code-switching and paraphrase
still land on the right label.

Why not an LLM for this
-----------------------
Measured on the build laptop (i5-4200U, no GPU): qwen2.5:3b needs ~23 s for a
five-token reply. The trained tier scores an utterance in ~1-3 ms, which is
what makes sub-150 ms on-device detection real rather than aspirational.

Layout
------
  datagen.py    synthetic labelled-utterance corpus generator (Roman-Urdu aware)
  train.py      TF-IDF (char_wb + word) -> one-vs-rest logistic regression -> ONNX
  classifier.py runtime inference wrapper used by the scoring pipeline

The golden set (tests/golden_set/) is NEVER used for training - it stays a
held-out evaluation set so scripts/eval.py numbers mean something.
"""

MODEL_DIR_ENV = "TRUSTGUARD_ML_DIR"
DEFAULT_MODEL_SUBDIR = "data/models"
MODEL_BASENAME = "tier15_taxonomy"

__all__ = ["MODEL_DIR_ENV", "DEFAULT_MODEL_SUBDIR", "MODEL_BASENAME"]
