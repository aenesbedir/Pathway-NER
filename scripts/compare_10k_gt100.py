#!/usr/bin/env python3
"""Measure the 10k dataset's pathway annotations against the human-reviewed
gt_100 ground truth (doccano/golden dataset/gt_100.jsonl), for the PMIDs that
appear in both.

Only PATHWAY spans are used. Reported side by side (never one replacing the
other):
  * exact — span-level set match on exact character offsets (the metric used
    in the earlier 10k-vs-gt_100 comparison)
  * partial — gold-coverage matching at a threshold (default 0.5), greedy
    one-to-one, identical logic to scripts/score_gt_100.py --partial

The 10k dataset plays the role of predictions; gt_100 is the gold.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.score_gt_100 import partial_confusion, prf  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="doccano/golden dataset/gt_100.jsonl")
    ap.add_argument("--tenk-matches", default="data/processed/pathway-10k/matches.jsonl")
    ap.add_argument("--partial", type=float, default=0.5)
    args = ap.parse_args()

    gt_by: dict[str, list[tuple[int, int]]] = {}
    for r in (json.loads(l) for l in Path(args.gt).open(encoding="utf-8")):
        gt_by[r["meta"]["pmid"]] = [
            (e["start_offset"], e["end_offset"])
            for e in r["entities"] if e["label"] == "PATHWAY"
        ]

    ten_by: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for r in (json.loads(l) for l in Path(args.tenk_matches).open(encoding="utf-8")):
        for s in r["spans"]:
            ten_by[r["pmid"]].add((s["start"], s["end"]))

    common = sorted(set(gt_by) & set(ten_by))
    print(f"common pmids: {len(common)}")

    exact_tp = exact_fp = exact_fn = 0
    ptp = pfp = pfn = 0
    for pmid in common:
        gs = set(gt_by[pmid])
        ts = ten_by[pmid]
        exact_tp += len(gs & ts)
        exact_fp += len(ts - gs)
        exact_fn += len(gs - ts)
        t, fp_, fn_ = partial_confusion(list(gs), list(ts), args.partial)
        ptp += t
        pfp += fp_
        pfn += fn_

    ep, er, ef = prf(exact_tp, exact_fp, exact_fn)
    pp, pr_, pf = prf(ptp, pfp, pfn)
    out = {
        "gold": args.gt,
        "predictions": "10k dataset (data/processed/pathway-10k/matches.jsonl)",
        "n_common_pmids": len(common),
        "exact_span": {"precision": ep, "recall": er, "f1": ef},
        "partial": {
            "threshold": args.partial,
            "precision": pp,
            "recall": pr_,
            "f1": pf,
        },
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
