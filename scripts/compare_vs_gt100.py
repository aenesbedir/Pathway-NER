#!/usr/bin/env python3
"""Measure any pathway-span source against the human-reviewed gt_100 ground
truth (doccano/golden_dataset/gt_100.jsonl).

Works for any JSONL whose records carry a `pmid` and a `spans` list of
{start, end, ...}, which covers both span sources in this repo:

  * the 10k dataset       data/processed/pathway-10k/matches.jsonl
                          (several records per PMID, one per pathway_id)
  * the local-LLM silver  data/silver/pathway_remaining_6125.jsonl
                          (qwen2.5:14b, one record per PMID)

The basis is ALL 100 gt_100 PMIDs. A PMID absent from the prediction file
counts as zero predictions rather than being dropped — matches.jsonl only
stores PMIDs that had at least one pathway hit (9168 of 10125), so
intersecting on it would silently discard exactly the recall failures.
Membership of gt_100 in the 10k dataset is established by
data/processed/pathway-10k/{articles,splits}.json, which hold all 10125 PMIDs.

Only PATHWAY spans are used. Reported side by side, never one replacing the
other:
  * exact — span-level set match on exact character offsets
  * partial — gold-coverage matching at a threshold (default 0.5), greedy
    one-to-one, identical logic to scripts/score_gt_100.py --partial
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.score_gt_100 import partial_confusion, prf  # noqa: E402


def load_gold(path: Path) -> dict[str, list[tuple[int, int]]]:
    gold = {}
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        gold[r["meta"]["pmid"]] = [
            (e["start_offset"], e["end_offset"])
            for e in r["entities"] if e["label"] == "PATHWAY"
        ]
    return gold


def load_pred(path: Path) -> dict[str, set[tuple[int, int]]]:
    pred: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        for s in r["spans"]:
            pred[str(r["pmid"])].add((s["start"], s["end"]))
    return pred


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="doccano/golden_dataset/gt_100.jsonl")
    ap.add_argument("--pred", required=True, help="JSONL with pmid + spans[{start,end}]")
    ap.add_argument("--label", default=None, help="name recorded in the output")
    ap.add_argument("--partial", type=float, default=0.5)
    args = ap.parse_args()

    gold = load_gold(Path(args.gt))
    pred = load_pred(Path(args.pred))

    etp = efp = efn = 0
    ptp = pfp = pfn = 0
    n_pred = n_gold = 0
    covered = 0
    for pmid, gs in gold.items():
        gset = set(gs)
        pset = pred.get(pmid, set())
        covered += pmid in pred
        n_pred += len(pset)
        n_gold += len(gset)
        etp += len(gset & pset)
        efp += len(pset - gset)
        efn += len(gset - pset)
        t, fp_, fn_ = partial_confusion(list(gset), list(pset), args.partial)
        ptp += t
        pfp += fp_
        pfn += fn_

    ep, er, ef = prf(etp, efp, efn)
    pp, pr_, pf = prf(ptp, pfp, pfn)
    print(json.dumps({
        "label": args.label or args.pred,
        "predictions": args.pred,
        "gold": args.gt,
        "n_pmids": len(gold),
        "n_pmids_present_in_pred": covered,
        "n_pred_spans": n_pred,
        "n_gold_spans": n_gold,
        "exact_span": {"precision": ep, "recall": er, "f1": ef},
        "partial": {"threshold": args.partial, "precision": pp,
                    "recall": pr_, "f1": pf},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
