#!/usr/bin/env python3
"""
score_against_review.py

Score a silver run against the reviewed batch-05 labels — an annotator-model A/B that
is far better powered than the golden set (10 abstracts / 76 mentions, with the
deciding metric resting on 6 cases).

Reference labels: analysis/batch_05_5_review.json, 200 abstracts.
    docs 1-50    human annotation (doccano export), the gold standard there
    docs 51-200  assistant review of the machine spans against ANNOTATION_GUIDE.md
Gold spans for a document are its `tp` + `fn` entries: what *should* have been marked.

Read the recall numbers as relative, not absolute. The reference sweep counts umbrella
mentions (`lipid metabolism`, `energy metabolism`) and repeat mentions that the guided
prompt was never aiming at, so absolute recall is pessimistic — but it is pessimistic
by the same amount for every model, which is what an A/B needs.

Run from repo root:
    venv310/bin/python3 analysis/score_against_review.py \\
        data/silver/eval_batch05_qwen2.5-14b.jsonl

    # compare two runs side by side
    venv310/bin/python3 analysis/score_against_review.py A.jsonl B.jsonl
"""

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "analysis/batch_05_5_review.json"
BATCH = ROOT / "doccano/batches/pilot_1k_doccano_batch_05_5.jsonl"


def load_reference():
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    texts = {json.loads(l)["meta"]["pmid"]: json.loads(l)["text"]
             for l in BATCH.read_text(encoding="utf-8").splitlines() if l.strip()}
    gold, half = {}, {}
    for d in review["documents"]:
        gold[d["pmid"]] = {(s["start"], s["end"]) for s in d["tp"] + d["fn"]}
        half[d["pmid"]] = "1-50" if d["doc_index_1based"] <= 50 else "51-200"
    return gold, half, texts


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score(path: Path, gold, half, texts):
    preds = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            preds[rec["pmid"]] = {(s["start"], s["end"]) for s in rec["spans"]}

    missing = [p for p in gold if p not in preds]
    buckets = {"all": [0, 0, 0], "1-50": [0, 0, 0], "51-200": [0, 0, 0]}
    lenient = [0, 0, 0]
    fp_txt, fn_txt = Counter(), Counter()

    for pmid, g in gold.items():
        p = preds.get(pmid, set())
        t = texts[pmid]
        for key in ("all", half[pmid]):
            buckets[key][0] += len(g & p)
            buckets[key][1] += len(p - g)
            buckets[key][2] += len(g - p)
        # lenient: a predicted span counts if it overlaps any gold span at all
        ov_p = {s for s in p if any(s[0] < b and a < s[1] for a, b in g)}
        ov_g = {s for s in g if any(s[0] < b and a < s[1] for a, b in p)}
        lenient[0] += len(ov_p)
        lenient[1] += len(p - ov_p)
        lenient[2] += len(g - ov_g)
        for a, b in sorted(p - g):
            fp_txt[t[a:b]] += 1
        for a, b in sorted(g - p):
            fn_txt[t[a:b]] += 1

    return {"name": path.name, "n_docs": len(preds), "missing": missing,
            "buckets": buckets, "lenient": lenient, "fp": fp_txt, "fn": fn_txt,
            "n_spans": sum(len(v) for v in preds.values())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path, help="silver .jsonl file(s) to score")
    ap.add_argument("--top", type=int, default=12, help="how many error strings to list")
    args = ap.parse_args()

    gold, half, texts = load_reference()
    n_gold = sum(len(v) for v in gold.values())
    print(f"Reference: {len(gold)} abstracts, {n_gold} gold spans "
          f"({REVIEW.relative_to(ROOT)})\n")

    results = [score(p, gold, half, texts) for p in args.runs]

    hdr = f"{'run':<38} {'spans':>6} {'TP':>5} {'FP':>5} {'FN':>5} {'P':>7} {'R':>7} {'F1':>7}"
    print("SPAN-EXACT")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        for key in ("all", "1-50", "51-200"):
            tp, fp, fn = r["buckets"][key]
            p, rc, f = prf(tp, fp, fn)
            label = r["name"] if key == "all" else f"    docs {key}"
            span = r["n_spans"] if key == "all" else ""
            print(f"{label:<38} {span:>6} {tp:>5} {fp:>5} {fn:>5} "
                  f"{p:>7.3f} {rc:>7.3f} {f:>7.3f}")
        print()

    print("LENIENT (predicted span overlaps a gold span)")
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        tp, fp, fn = r["lenient"]
        p, rc, f = prf(tp, fp, fn)
        print(f"{r['name']:<38} {r['n_spans']:>6} {tp:>5} {fp:>5} {fn:>5} "
              f"{p:>7.3f} {rc:>7.3f} {f:>7.3f}")

    for r in results:
        if r["missing"]:
            print(f"\n!! {r['name']}: {len(r['missing'])} abstract(s) absent from the run: "
                  f"{', '.join(r['missing'][:10])}")
        print(f"\n{r['name']} — top false positives")
        for s, n in r["fp"].most_common(args.top):
            print(f"   {n:>3}  {s}")
        print(f"{r['name']} — top false negatives")
        for s, n in r["fn"].most_common(args.top):
            print(f"   {n:>3}  {s}")


if __name__ == "__main__":
    main()
