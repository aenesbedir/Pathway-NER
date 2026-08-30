#!/usr/bin/env python3
"""
synth_probe_report.py

Score one synthetic batch against the teacher's blind re-labelling.

THROWAWAY PROBE. See `synth_kg_seed.py` for the framing.

This is the acceptance filter from MedSyn, applied to relation labels instead of
ICD codes: an example is kept only when a teacher reading the generated text with
no knowledge of what it was meant to say returns the label it was meant to carry.
MedSyn reported 64% acceptance for GPT-4-generated notes and 51% for a fine-tuned
LLaMA. That is the number this report produces, per method and per class.

The acceptance rate is the finding. A method that generates fluent text nothing
agrees with is a method that would have injected label noise into the student.

Inputs are a `--expected` file from a generator and a relations file from
`run_teacher.py` run over the same candidates. A generated example the teacher
declined to answer counts as `unlabelled`, not as a disagreement: the two
failures have different causes and lumping them would flatter whichever method
produced more unparsable text.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from schema import LABELS, read_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expected", type=Path, required=True)
    ap.add_argument("--relabelled", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    expected = {e["candidate_id"]: e for e in read_jsonl(args.expected)}
    got = {r.get("candidate_id", ""): r for r in read_jsonl(args.relabelled)}

    per_class: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    confusion: collections.Counter = collections.Counter()
    accepted = unlabelled = 0

    for cid, exp in expected.items():
        want = exp["expected_label"]
        row = got.get(cid)
        if row is None:
            per_class[want]["unlabelled"] += 1
            unlabelled += 1
            continue
        have = row["label"]
        per_class[want]["labelled"] += 1
        if have == want:
            per_class[want]["accepted"] += 1
            accepted += 1
        confusion[(want, have)] += 1

    method = next(iter(expected.values()), {}).get("method", "unknown")
    n = len(expected)
    report = {
        "method": method,
        "expected": str(args.expected),
        "relabelled": str(args.relabelled),
        "n_generated": n,
        "n_relabelled": n - unlabelled,
        "n_unlabelled": unlabelled,
        "acceptance_rate": round(accepted / n, 3) if n else 0.0,
        "per_class": {
            label: {
                "n": per_class[label]["labelled"] + per_class[label]["unlabelled"],
                "accepted": per_class[label]["accepted"],
                "unlabelled": per_class[label]["unlabelled"],
                "acceptance_rate": (
                    round(per_class[label]["accepted"] / total, 3)
                    if (total := per_class[label]["labelled"] + per_class[label]["unlabelled"])
                    else 0.0
                ),
            }
            for label in LABELS
            if label in per_class
        },
        "confusion": {
            f"{want}->{have}": c for (want, have), c in confusion.most_common()
        },
    }
    out = args.out or args.expected.with_name("probe_report.json")
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
