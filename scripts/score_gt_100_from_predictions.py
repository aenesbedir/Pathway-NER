"""Score sweep runs on gt_100 without the model weights.

scripts/score_gt_100.py loads a checkpoint and runs inference. A sweep launched
through run_matrix.py keeps no weights (--no-save-model: eighteen 0.5-1.6 GB
checkpoints do not fit), but it does keep test_predictions.jsonl, and every
gt_100 PMID sits in the test split of data/processed/pathway-10k-missing. The
predictions for those 100 abstracts are therefore already on disk.

This script recovers the character spans from those tag sequences. For each
PMID it re-tokenizes the abstract with the run's tokenizer, keeps the positions
train.py scored (labels != -100 in the tokenized test set, whose count is
verified against the prediction length), pairs them with the tokenizer's offset
mapping, and decodes B/I runs into spans. The spans are then compared with the
gt_100 gold spans using the same exact and partial metrics as score_gt_100.py.

A PMID absent from the predictions counts as zero predictions rather than being
dropped, matching score_gt_100.py.

Usage:
    python scripts/score_gt_100_from_predictions.py \
        --runs-dir runs-truba-10k-missing --output analysis/gt_100_10k_missing.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_GT = ROOT / "doccano/golden_dataset/gt_100.jsonl"
DATA = ROOT / "data/processed"


def decode_spans(tags, offsets):
    """Decode a B..I token sequence into (start, end) character spans."""
    spans, cur = [], None
    for tag, (s, e) in zip(tags, offsets):
        if tag == "B-Pathway":
            if cur is not None:
                spans.append(tuple(cur))
            cur = [s, e]
        elif tag == "I-Pathway":
            if cur is None:
                cur = [s, e]
            else:
                cur[1] = e
        elif cur is not None:
            spans.append(tuple(cur))
            cur = None
    if cur is not None:
        spans.append(tuple(cur))
    return spans


def partial_confusion(gold_spans, pred_spans, threshold=0.5):
    """Greedy one-to-one matching on gold coverage.

    threshold 0.5 is the metric score_gt_100.py reports as `partial`: a
    prediction counts for a gold span when it covers at least half of that
    span's characters. threshold 0.0 is the lenient variant - any character
    overlap counts - which is the usual reading of "TP by intersection".
    """
    candidates = []
    for g in gold_spans:
        glen = max(1, g[1] - g[0])
        for p in pred_spans:
            inter = max(0, min(g[1], p[1]) - max(g[0], p[0]))
            if inter > 0 and inter / glen >= threshold:
                candidates.append((inter / glen, g, p))
    candidates.sort(reverse=True, key=lambda c: c[0])
    used_g, used_p, tp = set(), set(), 0
    for _, g, p in candidates:
        if g in used_g or p in used_p:
            continue
        used_g.add(g)
        used_p.add(p)
        tp += 1
    return tp, len(pred_spans) - len(used_p), len(gold_spans) - len(used_g)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


def load_gold(path: Path):
    gold = {}
    for line in path.open(encoding="utf-8"):
        rec = json.loads(line)
        pmid = rec["meta"]["pmid"]
        spans = {
            (e["start_offset"], e["end_offset"])
            for e in rec.get("entities", [])
            if str(e.get("label", "")).upper().startswith("PATH")
        }
        gold[pmid] = {"text": rec["text"], "spans": spans}
    return gold


def score_run(run_dir: Path, gold: dict, cache: dict) -> dict | None:
    results = json.loads((run_dir / "test_results.json").read_text())
    model_key = results["model_key"]
    dataset = Path(results["data_dir"]).name
    meta = json.loads((DATA / dataset / "meta.json").read_text())

    key = (dataset, model_key)
    if key not in cache:
        tok = AutoTokenizer.from_pretrained(meta["tokenizer_id"])
        masks = {}
        for line in (DATA / dataset / "test.jsonl").open(encoding="utf-8"):
            rec = json.loads(line)
            masks[rec["pmid"]] = [x != -100 for x in rec["labels"]]
        cache[key] = (tok, masks, meta["max_tokens"])
    tok, masks, max_tokens = cache[key]

    preds = {}
    for line in (run_dir / "test_predictions.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        preds[str(rec["pmid"])] = rec["pred"]

    tp = fp = fn = 0
    ptp = pfp = pfn = 0
    ltp = lfp = lfn = 0
    n_pred_spans = 0
    missing_pmids = 0

    for pmid, g in gold.items():
        gold_spans = g["spans"]
        tags = preds.get(pmid)
        if tags is None:
            missing_pmids += 1
            fn += len(gold_spans)
            pfn += len(gold_spans)
            lfn += len(gold_spans)
            continue

        enc = tok(g["text"], max_length=max_tokens, truncation=True,
                  return_offsets_mapping=True)
        mask = masks[pmid]
        if len(mask) != len(enc["input_ids"]):
            raise SystemExit(f"{pmid}: mask {len(mask)} != tokens "
                             f"{len(enc['input_ids'])} for {model_key}")
        offsets = [o for o, keep in zip(enc["offset_mapping"], mask) if keep]
        if len(offsets) != len(tags):
            raise SystemExit(f"{pmid}: {len(offsets)} scored positions vs "
                             f"{len(tags)} predictions for {run_dir}")

        pred_spans = decode_spans(tags, offsets)
        n_pred_spans += len(pred_spans)
        pset = set(pred_spans)
        hit = gold_spans & pset
        tp += len(hit)
        fp += len(pset) - len(hit)
        fn += len(gold_spans) - len(hit)

        a, b, c = partial_confusion(gold_spans, pred_spans)
        ptp += a
        pfp += b
        pfn += c

        a, b, c = partial_confusion(gold_spans, pred_spans, threshold=0.0)
        ltp += a
        lfp += b
        lfn += c

    p, r, f = prf(tp, fp, fn)
    pp, pr, pf = prf(ptp, pfp, pfn)
    lp, lr_, lf = prf(ltp, lfp, lfn)
    return {
        "run_dir": str(run_dir if run_dir.is_absolute() and ROOT not in run_dir.parents
                       else run_dir.relative_to(ROOT)),
        "model_key": model_key,
        "lr": results["lr"],
        "seed": results["seed"],
        "dataset": dataset,
        "test_f1_on_split": results["test_f1"],
        "gt100_exact_f1": f,
        "gt100_exact_p": p,
        "gt100_exact_r": r,
        "gt100_partial_f1": pf,
        "gt100_partial_p": pp,
        "gt100_partial_r": pr,
        "gt100_lenient_f1": lf,
        "gt100_lenient_p": lp,
        "gt100_lenient_r": lr_,
        "pred_spans": n_pred_spans,
        "pmids_without_predictions": missing_pmids,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default="runs-truba-10k-missing")
    ap.add_argument("--output", default="analysis/gt_100_from_predictions.json")
    ap.add_argument("--gt", default=str(DEFAULT_GT),
                    help="gold file; gt_100 or gt_125, same shape")
    args = ap.parse_args()

    gt_path = Path(args.gt)
    gold = load_gold(gt_path)
    n_gold = sum(len(g["spans"]) for g in gold.values())

    cache: dict = {}
    rows = []
    for res in sorted((ROOT / args.runs_dir).rglob("test_results.json")):
        rows.append(score_run(res.parent, gold, cache))

    rows.sort(key=lambda r: -r["gt100_exact_f1"])
    out = {
        "gold": {"file": str(gt_path), "pmids": len(gold),
                 "spans": n_gold},
        "runs": rows,
    }
    (ROOT / args.output).write_text(json.dumps(out, indent=1) + "\n")

    print(f"{gt_path.name}: {len(gold)} pmids, {n_gold} gold spans\n")
    print(f"{'exact':>7} {'part.5':>7} {'lenient':>8} {'len_P':>6} {'len_R':>6}"
          f" {'split':>7}  {'model':20} {'lr':>7} {'seed':>4}")
    for r in rows:
        print(f"{r['gt100_exact_f1']:7.4f} {r['gt100_partial_f1']:7.4f} "
              f"{r['gt100_lenient_f1']:8.4f} {r['gt100_lenient_p']:6.3f} "
              f"{r['gt100_lenient_r']:6.3f} {r['test_f1_on_split']:7.4f}  "
              f"{r['model_key']:20} {r['lr']:>7} {r['seed']:>4}")


if __name__ == "__main__":
    main()
