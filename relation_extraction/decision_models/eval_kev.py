#!/usr/bin/env python3
"""Score a Kev checkpoint on labelled relation requests.

kev.benchmark rejects states over 384 tokens for the released checkpoints, which
drops most abstracts, so this script scores every record with the limit raised.
Scores measure agreement with the silver labels, not accuracy.

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
            "opus": rec["questions"]["relation"]["label"],
            "pred": max(probs, key=probs.get),
            "probs": probs,
        })
    secs = time.time() - start
    with open(args.out, "w") as fh:
        json.dump(rows, fh)

    f1 = {}
    for label in labels:
        tp = sum(r["pred"] == label == r["opus"] for r in rows)
        fp = sum(r["pred"] == label != r["opus"] for r in rows)
        fn = sum(r["opus"] == label != r["pred"] for r in rows)
        f1[label] = round(2 * tp / (2 * tp + fp + fn), 3) if tp else 0.0
    accuracy = sum(r["pred"] == r["opus"] for r in rows) / len(rows)
    macro = sum(v for k, v in f1.items() if k != "no_association_stated") / 4
    print("n", len(rows), "acc", round(accuracy, 3), "macroF1_4", round(macro, 3))
    print("F", f1)
    print("pred", dict(collections.Counter(r["pred"] for r in rows)),
          "s_per_pair", round(secs / len(rows), 3),
          "peak_gib", round(torch.cuda.max_memory_reserved() / 2**30, 2))


if __name__ == "__main__":
    main()
