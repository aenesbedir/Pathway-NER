"""Score the missing-pathway span sources against the 25 curated abstracts.

gt_125 = gt_100 plus 25 abstracts from the missing-pathway test split, curated by
hand. Those 25 are the only place where the silver pipeline that built the
missing corpus can be measured against human judgement, so this script scores
each stage of it on exactly those 25 documents:

    ner            the pathway-10k checkpoint alone
    ner+booster    plus the deterministic pattern rules
    merged         plus the surface-form dictionary - what paironly_stages.jsonl holds
    reviewed       merged after scripts/apply_llm_review.py dropped the spans an
                   LLM audit called wrong - what went into the training data

Comparing `merged` with `reviewed` measures the audit itself: whether dropping
those spans moved precision without costing recall.

Two metrics, the same pair gt_100_scores.json reports: exact character-offset set
match, and partial gold-coverage at threshold 0.5.

Usage:
    python scripts/score_gt_125_span_sources.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT125 = ROOT / "doccano/golden_dataset/gt_125/gt_125.jsonl"
STAGES = ROOT / "data/processed/missing_pathways/paironly_stages.jsonl"
REVIEWED = ROOT / "data/processed/missing_pathways/missing_llm_review.jsonl"
OUT = ROOT / "doccano/golden_dataset/gt_125/gt_125_span_sources.json"


def partial_confusion(gold, pred, threshold=0.5):
    cands = []
    for g in gold:
        glen = max(1, g[1] - g[0])
        for p in pred:
            inter = max(0, min(g[1], p[1]) - max(g[0], p[0]))
            if inter > 0 and inter / glen >= threshold:
                cands.append((inter / glen, g, p))
    cands.sort(reverse=True, key=lambda c: c[0])
    ug, up, tp = set(), set(), 0
    for _, g, p in cands:
        if g in ug or p in up:
            continue
        ug.add(g)
        up.add(p)
        tp += 1
    return tp, len(pred) - len(up), len(gold) - len(ug)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


def score(gold_by_pmid, pred_by_pmid):
    tp = fp = fn = 0
    ptp = pfp = pfn = 0
    n_pred = 0
    for pmid, gold in gold_by_pmid.items():
        pred = pred_by_pmid.get(pmid, set())
        n_pred += len(pred)
        hit = gold & pred
        tp += len(hit)
        fp += len(pred) - len(hit)
        fn += len(gold) - len(hit)
        a, b, c = partial_confusion(gold, pred)
        ptp += a
        pfp += b
        pfn += c
    p, r, f = prf(tp, fp, fn)
    pp, pr, pf = prf(ptp, pfp, pfn)
    return {
        "pred_spans": n_pred,
        "exact": {"f1": f, "precision": p, "recall": r,
                  "tp": tp, "fp": fp, "fn": fn},
        "partial": {"threshold": 0.5, "f1": pf, "precision": pp, "recall": pr},
    }


def main() -> None:
    gold = {}
    for line in GT125.open(encoding="utf-8"):
        rec = json.loads(line)
        if rec["meta"].get("annotation_status") != "human_curated":
            continue
        gold[rec["meta"]["pmid"]] = {
            (e["start_offset"], e["end_offset"]) for e in rec["entities"]
        }

    stages = {json.loads(l)["pmid"]: json.loads(l)
              for l in STAGES.open(encoding="utf-8")}
    reviewed = {json.loads(l)["pmid"]: json.loads(l)
                for l in REVIEWED.open(encoding="utf-8")}

    def pick(src, pmids, keep):
        return {p: {(s["start"], s["end"]) for s in src[p]["spans"]
                    if s["source"] in keep}
                for p in pmids if p in src}

    pmids = set(gold)
    sources = {
        "ner": pick(stages, pmids, {"ner"}),
        "ner+booster": pick(stages, pmids, {"ner", "booster"}),
        "merged": pick(stages, pmids, {"ner", "booster", "dict"}),
        "reviewed": pick(reviewed, pmids, {"ner", "booster", "dict"}),
        "dict_only": pick(stages, pmids, {"dict"}),
    }

    review = {}
    for line in (ROOT / "data/processed/missing_pathways/llm_review.jsonl").open(
            encoding="utf-8"):
        rec = json.loads(line)
        if rec.get("error") or rec["pmid"] not in gold:
            continue
        review[rec["pmid"]] = rec

    # Agreement between the LLM audit's per-span verdict and the curator, which
    # is what the audit can be judged on here: it dropped no span in these 25,
    # so its removals cannot be scored, only its opinions.
    agree = Counter()
    for pmid, rec in review.items():
        g = gold[pmid]
        for v in rec["review"].get("spans") or []:
            i = v.get("i")
            if not isinstance(i, int) or i >= len(rec["spans"]):
                continue
            sp = rec["spans"][i]
            key = (sp["start"], sp["end"])
            verdict = v.get("verdict", "?")
            kept = key in g
            overlaps = any(key[0] < b[1] and b[0] < key[1] for b in g)
            if kept:
                outcome = "curator_kept_exactly"
            elif overlaps:
                outcome = "curator_moved_boundary"
            else:
                outcome = "curator_removed"
            agree[f"{verdict} -> {outcome}"] += 1

    dropped = Counter()
    for p in pmids:
        before = {(s["start"], s["end"]) for s in stages[p]["spans"]}
        after = {(s["start"], s["end"]) for s in reviewed[p]["spans"]}
        for span in before - after:
            dropped["dropped_by_review"] += 1
            dropped["dropped_and_in_gold"] += 1 if span in gold[p] else 0

    out = {
        "ground_truth": str(GT125.relative_to(ROOT)),
        "basis": {
            "n_docs": len(gold),
            "n_gold_pathway_spans": sum(len(v) for v in gold.values()),
            "rule": "the 25 human-curated abstracts of gt_125 only; the gt_100 "
                    "half has no silver counterpart to score",
        },
        "notes": "Stages of the pipeline that produced the missing-pathway "
                 "corpus, scored against the human curation of the same 25 "
                 "abstracts. `reviewed` is `merged` after an LLM audit removed "
                 "the spans it judged wrong; the audit ran through the raw "
                 "Claude CLI (scripts/review_missing_dataset.py), which uses "
                 "the session's configured model rather than a pinned one, so "
                 "the exact model id is not recorded in the artefacts.",
        "review_effect": dict(dropped),
        "review_verdict_vs_curator": dict(agree),
        "review_verdict_note": "the audit dropped no span in these 25, so only "
                               "its verdicts can be compared, not its removals",
        "sources": {k: score(gold, v) for k, v in sources.items()},
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")

    print(f"gold: {out['basis']['n_docs']} docs, "
          f"{out['basis']['n_gold_pathway_spans']} spans\n")
    print(f"{'source':14} {'spans':>6} {'exact_F1':>9} {'P':>6} {'R':>6} "
          f"{'part_F1':>8} {'TP':>4} {'FP':>4} {'FN':>4}")
    for k, v in out["sources"].items():
        e = v["exact"]
        print(f"{k:14} {v['pred_spans']:6d} {e['f1']:9.4f} {e['precision']:6.3f} "
              f"{e['recall']:6.3f} {v['partial']['f1']:8.4f} "
              f"{e['tp']:4d} {e['fp']:4d} {e['fn']:4d}")
    print(f"\nreview dropped {dropped['dropped_by_review']} spans here, "
          f"{dropped['dropped_and_in_gold']} of which the curator kept")
    print("\nLLM verdict vs curator:")
    for k, v in sorted(agree.items(), key=lambda x: -x[1]):
        print(f"  {v:4d}  {k}")


if __name__ == "__main__":
    main()
