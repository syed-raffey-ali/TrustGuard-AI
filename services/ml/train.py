"""Train the multi-label taxonomy classifier (the "trained tier").

Model choice rationale
----------------------
TF-IDF over character n-grams (char_wb 2-5) unioned with word n-grams (1-2),
fed to one-vs-rest logistic regression.

Character n-grams are the deliberate choice, not a shortcut: Roman Urdu has no
fixed orthography, so "batao"/"btao"/"bata do" and "paisay"/"paise"/"pesay" are
the same intent spelled five ways. Word-level features alone would treat them as
unrelated tokens. Character n-grams share substructure, which is exactly the
"scammer rephrases slightly and is still caught" requirement.

Logistic regression (not a transformer) because it trains in seconds on a
2-core CPU, infers in ~1-3 ms, and emits calibrated per-label probabilities that
feed straight into the deterministic scorer's confidence field. A transformer
would need a GPU this laptop does not have and would blow the latency budget.

Per-label decision thresholds are tuned on a held-out split to maximise F1, then
persisted - a single global 0.5 threshold badly underperforms on rare labels.

Usage
-----
    .venv/bin/python -m ml.train --corpus data/train/corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MultiLabelBinarizer

_HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from ml import MODEL_BASENAME  # noqa: E402
from scoring.taxonomy import COUNTER_LABELS, LABELS, SCAM_LABELS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(_HERE))


def load_corpus(path: str) -> tuple[list[str], list[list[str]], list[list[str]]]:
    texts, labels, template_ids = [], [], []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(row["labels"])
            template_ids.append(row.get("template_ids", []))
    return texts, labels, template_ids


def template_disjoint_split(
    texts: list[str],
    Y: np.ndarray,
    template_ids: list[list[str]],
    holdout_frac: float,
    seed: int,
) -> tuple[list[str], list[str], np.ndarray, np.ndarray, dict]:
    """Split so that validation phrasings were never seen during training.

    A plain random row split scores ~1.00 F1 on synthetic data because every
    validation row is a slot-permutation of a template the model already
    memorised. That number is meaningless. Holding out whole templates measures
    the property we actually care about: a scammer rephrasing the ask in words
    the lexicon never anticipated should still be caught.

    Per label we reserve at least one template for validation, so every label is
    genuinely tested on unseen phrasing.
    """
    rng = np.random.RandomState(seed)

    by_group: dict[str, list[str]] = {}
    for tids in template_ids:
        for tid in tids:
            group = tid.split("#", 1)[0]
            by_group.setdefault(group, [])
            if tid not in by_group[group]:
                by_group[group].append(tid)

    holdout: set[str] = set()
    for group, tids in by_group.items():
        tids = sorted(tids)
        k = max(1, int(round(len(tids) * holdout_frac)))
        k = min(k, len(tids) - 1) if len(tids) > 1 else 0
        if k:
            picked = rng.choice(len(tids), size=k, replace=False)
            holdout.update(tids[i] for i in picked)

    # A row goes to validation only if EVERY template it came from is held out;
    # rows mixing a seen and an unseen template are dropped to keep the split clean.
    tr_idx, va_idx, dropped = [], [], 0
    for i, tids in enumerate(template_ids):
        if not tids:
            tr_idx.append(i)
            continue
        held = sum(1 for t in tids if t in holdout)
        if held == 0:
            tr_idx.append(i)
        elif held == len(tids):
            va_idx.append(i)
        else:
            dropped += 1

    info = {
        "strategy": "template_disjoint",
        "held_out_templates": len(holdout),
        "total_templates": sum(len(v) for v in by_group.values()),
        "rows_dropped_mixed": dropped,
    }
    X_tr = [texts[i] for i in tr_idx]
    X_va = [texts[i] for i in va_idx]
    return X_tr, X_va, Y[tr_idx], Y[va_idx], info


def build_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("char", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            min_df=2,
            max_features=200_000,
            sublinear_tf=True,
            lowercase=True,
        )),
        ("word", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=2,
            max_features=80_000,
            sublinear_tf=True,
            lowercase=True,
        )),
    ])
    clf = OneVsRestClassifier(
        LogisticRegression(
            C=8.0,
            max_iter=2000,
            class_weight="balanced",
            solver="liblinear",
        ),
        # n_jobs=1 deliberately: joblib's memmap hand-off to liblinear raises
        # "WRITEBACKIFCOPY base is read-only" on this sklearn/joblib pair, and
        # sequential liblinear on sparse TF-IDF fits in well under a minute anyway.
        n_jobs=1,
    )
    return Pipeline([("features", features), ("clf", clf)])


def tune_thresholds(
    y_true: np.ndarray, y_prob: np.ndarray, classes: list[str]
) -> dict[str, float]:
    """Per-label threshold maximising F1 on the validation split."""
    grid = np.arange(0.10, 0.91, 0.02)
    thresholds: dict[str, float] = {}
    for j, label in enumerate(classes):
        truth = y_true[:, j]
        if truth.sum() == 0:
            thresholds[label] = 0.50
            continue
        best_t, best_f1 = 0.50, -1.0
        for t in grid:
            pred = (y_prob[:, j] >= t).astype(int)
            _, _, f1, _ = precision_recall_fscore_support(
                truth, pred, average="binary", zero_division=0
            )
            if f1 > best_f1:
                best_f1, best_t = f1, float(t)
        thresholds[label] = round(best_t, 3)
    return thresholds


def evaluate(
    y_true: np.ndarray, y_prob: np.ndarray, classes: list[str], thresholds: dict[str, float]
) -> dict:
    thr = np.array([thresholds[c] for c in classes])
    y_pred = (y_prob >= thr).astype(int)

    micro = precision_recall_fscore_support(y_true, y_pred, average="micro", zero_division=0)
    macro = precision_recall_fscore_support(y_true, y_pred, average="macro", zero_division=0)

    per_label = {}
    for j, label in enumerate(classes):
        p, r, f1, _ = precision_recall_fscore_support(
            y_true[:, j], y_pred[:, j], average="binary", zero_division=0
        )
        per_label[label] = {
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1": round(float(f1), 4),
            "support": int(y_true[:, j].sum()),
            "threshold": thresholds[label],
            "weight": LABELS[label].weight,
            "family": LABELS[label].family,
        }

    # Benign guard: rows with no true label must produce no prediction.
    benign_rows = y_true.sum(axis=1) == 0
    benign_clean = (
        float((y_pred[benign_rows].sum(axis=1) == 0).mean()) if benign_rows.any() else None
    )

    return {
        "micro": {"precision": round(float(micro[0]), 4),
                  "recall": round(float(micro[1]), 4),
                  "f1": round(float(micro[2]), 4)},
        "macro": {"precision": round(float(macro[0]), 4),
                  "recall": round(float(macro[1]), 4),
                  "f1": round(float(macro[2]), 4)},
        "benign_no_false_fire_rate": round(benign_clean, 4) if benign_clean is not None else None,
        "per_label": per_label,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=os.path.join(ROOT, "data", "train", "corpus.jsonl"))
    ap.add_argument("--extra", action="append", default=[],
                    help="additional corpus file(s), e.g. data/train/augmented.jsonl "
                         "(repeatable)")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "data", "models"))
    ap.add_argument("--test-size", type=float, default=0.18,
                    help="fraction of TEMPLATES held out (or of rows with --random-split)")
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--random-split", action="store_true",
                    help="use a plain row split - inflated on synthetic data, for comparison only")
    ap.add_argument("--onnx", action="store_true", help="also attempt an ONNX export")
    args = ap.parse_args()

    if not os.path.exists(args.corpus):
        raise SystemExit(
            f"corpus not found: {args.corpus}\n"
            "generate it first:  PYTHONPATH=services .venv/bin/python -m ml.datagen"
        )

    texts, label_lists, template_ids = load_corpus(args.corpus)
    print(f"corpus: {len(texts)} samples")

    for extra in args.extra:
        if not os.path.exists(extra):
            print(f"  [skip] {extra} not found")
            continue
        e_texts, e_labels, e_tids = load_corpus(extra)
        texts += e_texts
        label_lists += e_labels
        template_ids += e_tids
        print(f"  + {len(e_texts)} from {os.path.relpath(extra, ROOT)}")
    if args.extra:
        print(f"combined: {len(texts)} samples")

    all_labels = sorted(SCAM_LABELS | COUNTER_LABELS)
    mlb = MultiLabelBinarizer(classes=all_labels)
    Y = mlb.fit_transform(label_lists)
    classes = list(mlb.classes_)
    print(f"labels: {len(classes)}")

    if args.random_split:
        X_tr, X_va, y_tr, y_va = train_test_split(
            texts, Y, test_size=args.test_size, random_state=args.seed
        )
        split_info = {"strategy": "random_row",
                      "warning": "optimistic on synthetic data - templates leak across splits"}
    else:
        X_tr, X_va, y_tr, y_va, split_info = template_disjoint_split(
            texts, Y, template_ids, args.test_size, args.seed
        )
    print(f"split: {split_info}")
    print(f"train: {len(X_tr)}   val: {len(X_va)}")

    pipe = build_pipeline()
    started = time.perf_counter()
    pipe.fit(X_tr, y_tr)
    train_s = time.perf_counter() - started
    print(f"fit completed in {train_s:.1f}s")

    y_prob = pipe.predict_proba(X_va)
    thresholds = tune_thresholds(y_va, y_prob, classes)
    metrics = evaluate(y_va, y_prob, classes, thresholds)

    # inference latency - the number that justifies this tier existing
    sample = X_va[:200]
    t0 = time.perf_counter()
    pipe.predict_proba(sample)
    per_utterance_ms = (time.perf_counter() - t0) * 1000 / len(sample)

    os.makedirs(args.out_dir, exist_ok=True)
    model_path = os.path.join(args.out_dir, f"{MODEL_BASENAME}.joblib")
    joblib.dump(
        {"pipeline": pipe, "classes": classes, "thresholds": thresholds,
         "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        model_path,
        compress=3,
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus": os.path.relpath(args.corpus, ROOT),
        "extra_corpora": [os.path.relpath(e, ROOT) for e in args.extra
                          if os.path.exists(e)],
        "corpus_size": len(texts),
        "train_size": len(X_tr),
        "val_size": len(X_va),
        "split": split_info,
        "labels": len(classes),
        "fit_seconds": round(train_s, 2),
        "inference_ms_per_utterance": round(per_utterance_ms, 3),
        "model_path": os.path.relpath(model_path, ROOT),
        "metrics": metrics,
        "note": "Trained on synthetic corpus only. tests/golden_set/ is held out "
                "so scripts/eval.py remains an honest measurement.",
    }
    report_path = os.path.join(args.out_dir, f"{MODEL_BASENAME}_report.json")
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2)

    if args.onnx:
        _try_onnx(pipe, classes, args.out_dir, X_va[:50])

    print("\n================ TRAINED TIER ================")
    print(f"micro  P={metrics['micro']['precision']:.3f} "
          f"R={metrics['micro']['recall']:.3f} F1={metrics['micro']['f1']:.3f}")
    print(f"macro  P={metrics['macro']['precision']:.3f} "
          f"R={metrics['macro']['recall']:.3f} F1={metrics['macro']['f1']:.3f}")
    print(f"benign no-false-fire  {metrics['benign_no_false_fire_rate']}")
    print(f"inference             {per_utterance_ms:.2f} ms/utterance")
    print(f"model                 {model_path}")
    print(f"report                {report_path}")

    worst = sorted(metrics["per_label"].items(), key=lambda kv: kv[1]["f1"])[:5]
    print("\nweakest labels:")
    for name, m in worst:
        print(f"  {name:<42} F1={m['f1']:.3f} (P={m['precision']:.2f} R={m['recall']:.2f})")


def _try_onnx(pipe, classes, out_dir: str, sample: list[str]) -> None:
    """Attempt ONNX export and verify parity. Reports honestly if unsupported.

    skl2onnx's TfidfVectorizer converter has known gaps around char_wb
    tokenisation, so parity is verified rather than assumed. The joblib artifact
    stays the source of truth for the backend either way.
    """
    try:
        from skl2onnx import to_onnx
        from skl2onnx.common.data_types import StringTensorType
        import onnxruntime as ort
    except ImportError as exc:
        print(f"[onnx] skipped - {exc}")
        return

    path = os.path.join(out_dir, f"{MODEL_BASENAME}.onnx")
    try:
        onx = to_onnx(
            pipe,
            initial_types=[("input", StringTensorType([None, 1]))],
            options={id(pipe.named_steps["clf"]): {"zipmap": False}},
            target_opset=15,
        )
        with open(path, "wb") as fh:
            fh.write(onx.SerializeToString())

        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        arr = np.array(sample, dtype=object).reshape(-1, 1)
        onnx_prob = sess.run(None, {"input": arr})[1]
        skl_prob = pipe.predict_proba(sample)
        max_diff = float(np.abs(np.asarray(onnx_prob) - skl_prob).max())
        if max_diff < 1e-3:
            print(f"[onnx] exported + parity verified (max diff {max_diff:.2e}) -> {path}")
        else:
            print(f"[onnx] PARITY FAILED (max diff {max_diff:.3f}) - "
                  f"char_wb tokenisation mismatch; joblib remains authoritative")
    except Exception as exc:  # noqa: BLE001 - export is best-effort by design
        print(f"[onnx] export failed: {type(exc).__name__}: {exc}")
        print("[onnx] joblib artifact is authoritative; on-device tier keeps using "
              "Tier-1 regex + gateway call")


if __name__ == "__main__":
    main()
