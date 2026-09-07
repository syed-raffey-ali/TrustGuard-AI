#!/usr/bin/env python3
"""Validate + summarise the golden set (Bible Appendix E distribution rules).

The 60 conversation files themselves are authored data under tests/golden_set/.
This script enforces the schema/distribution contract before eval.py runs.
"""

from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(ROOT, "tests", "golden_set")

REQUIRED_KEYS = {"id", "label", "expected_band", "family", "language", "channel", "messages"}
BANDS = {"low", "medium", "high", "critical"}
LABELS = {"scam", "safe", "injection"}
LANGS = {"english", "roman_urdu", "urdu", "mixed"}


def main() -> int:
    files = sorted(glob.glob(os.path.join(GOLDEN_DIR, "gs_*.json")))
    errors: list[str] = []
    stats = {"label": {}, "language": {}, "channel": {}}
    families: set[str] = set()

    for path in files:
        with open(path) as fh:
            conv = json.load(fh)
        cid = os.path.basename(path)[:-5]
        missing = REQUIRED_KEYS - set(conv)
        if missing:
            errors.append(f"{cid}: missing keys {missing}")
            continue
        if conv["id"] != cid:
            errors.append(f"{cid}: id mismatch ({conv['id']})")
        if conv["label"] not in LABELS:
            errors.append(f"{cid}: bad label {conv['label']}")
        if conv["expected_band"] not in BANDS:
            errors.append(f"{cid}: bad expected_band {conv['expected_band']}")
        if conv["language"] not in LANGS:
            errors.append(f"{cid}: bad language {conv['language']}")
        if len(conv["messages"]) < 4:
            errors.append(f"{cid}: too few messages ({len(conv['messages'])})")
        ids = [m.get("message_id") for m in conv["messages"]]
        if len(ids) != len(set(ids)):
            errors.append(f"{cid}: duplicate message_ids")
        for m in conv["messages"]:
            if m.get("speaker") not in ("them", "me"):
                errors.append(f"{cid}: bad speaker {m.get('speaker')!r}")
                break
        stats["label"][conv["label"]] = stats["label"].get(conv["label"], 0) + 1
        stats["language"][conv["language"]] = stats["language"].get(conv["language"], 0) + 1
        stats["channel"][conv.get("channel", "?")] = stats["channel"].get(conv.get("channel", "?"), 0) + 1
        families.add(conv.get("family", "?"))

    n = len(files)
    ru_like = sum(v for k, v in stats["language"].items() if k in ("roman_urdu", "mixed", "urdu"))
    print(f"files: {n}")
    print(f"label:    {stats['label']}")
    print(f"language: {stats['language']}  (roman-urdu-like: {ru_like}/{n} = {ru_like * 100 // max(n, 1)}%)")
    print(f"channel:  {stats['channel']}")
    print(f"families covered: {len(families)}")

    problems = []
    if n != 60:
        problems.append(f"need exactly 60 conversations, found {n}")
    if ru_like * 100 < 40 * n:
        problems.append("Roman Urdu/mixed/urdu share below 40%")
    for label, want in (("scam", 35), ("safe", 20), ("injection", 5)):
        got = stats["label"].get(label, 0)
        if got != want:
            problems.append(f"label {label}: want {want}, got {got}")

    if errors:
        print("\nERRORS:")
        for e in errors[:40]:
            print(" -", e)
    if problems:
        print("\nDISTRIBUTION PROBLEMS:")
        for p in problems:
            print(" -", p)
    if errors or problems:
        return 1
    print("\ngolden set OK ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
