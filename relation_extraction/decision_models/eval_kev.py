#!/usr/bin/env python3
"""Score a Kev checkpoint on labelled relation requests.

kev.benchmark rejects states over 384 tokens for the released checkpoints, which
drops most abstracts, so this script scores every record with the limit raised.
On the silver slices scores measure agreement with the silver labels, not accuracy.

macroF1_4 averages the four labels other than no_association_stated.
macroF1_present averages every label the reference uses, the way
train_relation_evidence.py computes its macro_f1. Records carrying a stratum in
_meta (gt_100) are also scored per stratum.

Usage (from the Kev checkout that train_kev.sh prepares, with its environment):
    .venv/bin/python <repo>/relation_extraction/decision_models/eval_kev.py \
        --run <checkpoint> --data <dir>/dev.jsonl --out <file>.json
"""
from __future__ import annotations

import argparse
import collections
import json
import time

import torch
from kev.checkpoint import LoadOptions
from kev.data import load_records
from kev.model import training_context
from kev.predictors import LocalPredictor


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="checkpoint directory or Hub id")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-state", type=int, default=3000)
    ap.add_argument("--dtype", choices=["fp32", "bf16"], default=None,
                    help="default: fp32, or bf16 for a checkpoint trained on a bf16 backbone")
    args = ap.parse_args()

    dtype = {"fp32": torch.float32, "bf16": torch.bfloat16, None: None}[args.dtype]
    predictor = LocalPredictor(args.run, "cuda", opts=LoadOptions(dtype=dtype),
                               context=training_context(args.max_state))
    records = load_records(args.data)
    labels = list(records[0]["questions"]["relation"]["criteria"])

    rows = []
    start = time.time()
    for rec in records:
        probs = predictor(rec)["probabilities"]["relation"]
        rows.append({
            "rid": rec["_meta"]["rid"],
            "stratum": rec["_meta"].get("stratum"),
            "opus": rec["questions"]["relation"]["label"],
            "pred": max(probs, key=probs.get),
            "probs": probs,
        })
    secs = time.time() - start
    with open(args.out, "w") as fh:
        json.dump(rows, fh)

    report(rows, labels)
    for stratum in sorted({r["stratum"] for r in rows} - {None}):
        print(f"-- stratum {stratum}")
        report([r for r in rows if r["stratum"] == stratum], labels)
    print("s_per_pair", round(secs / len(rows), 3),
          "peak_gib", round(torch.cuda.max_memory_reserved() / 2**30, 2))


def report(rows: list, labels: list) -> None:
    f1 = {}
    for label in labels:
        tp = sum(r["pred"] == label == r["opus"] for r in rows)
        fp = sum(r["pred"] == label != r["opus"] for r in rows)
        fn = sum(r["opus"] == label != r["pred"] for r in rows)
        f1[label] = round(2 * tp / (2 * tp + fp + fn), 3) if tp else 0.0
    accuracy = sum(r["pred"] == r["opus"] for r in rows) / len(rows)
    macro = sum(v for k, v in f1.items() if k != "no_association_stated") / 4
    present = [f1[label] for label in labels if any(r["opus"] == label for r in rows)]
    print("n", len(rows), "acc", round(accuracy, 3), "macroF1_4", round(macro, 3),
          "macroF1_present", round(sum(present) / len(present), 3))
    print("F", f1)
    print("gold", dict(collections.Counter(r["opus"] for r in rows)))
    print("pred", dict(collections.Counter(r["pred"] for r in rows)))


if __name__ == "__main__":
    main()
