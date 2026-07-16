#!/usr/bin/env python3
"""
eval_llm_guided.py

Phase 3 / P3-0: measure the guided LLM extraction on the golden set BEFORE any
scaling. Reports precision (the primary question) and variation recall, and
supports comparing models and the with/without-vocab prompt variants.

Scoring is offset-based against golden_set.json:
  - POS gold intervals  = every `spans` entry + every `shared_head_enumerations`
    phrase (real pathway mentions).
  - NEG gold intervals  = `metabolites_not_pathways` + `out_of_vocab_pathways`
    (must NOT be tagged).
Each grounded LLM mention is classified by interval overlap:
  - TP        : overlaps a POS interval
  - FP_neg    : overlaps a NEG interval (and no POS) — a real precision error
  - UNLABELED : overlaps neither — either a pathway we didn't annotate, or an FP;
                left for manual inspection (reported, not auto-judged).

Recall is reported per match_type over the contiguous `spans`, plus coarse
coverage of the enumeration phrases.

Run from repo root:
    venv310/bin/python3 playground/golden_set/eval_llm_guided.py \
        --model qwen2.5:7b [--vocab]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "llm"))

from booster import boost, merge  # noqa: E402
from extract_guided import extract_guided, DEFAULT_MODEL  # noqa: E402

GOLDEN = ROOT / "playground/golden_set/golden_set.json"
VOCAB_FILE = ROOT / "unique_pathways_from_recon.json"
QUERY_MATCHES = ROOT / "data/processed/exact_matches.jsonl"


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def load_query_pathways() -> dict[str, list[str]]:
    """pmid -> sorted list of query pathway_ids that retrieved it."""
    by_pmid: dict[str, set[str]] = {}
    if not QUERY_MATCHES.exists():
        return {}
    for line in QUERY_MATCHES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        by_pmid.setdefault(str(rec["pmid"]), set()).add(rec["pathway_id"])
    return {k: sorted(v) for k, v in by_pmid.items()}


def gold_intervals(article: dict):
    """Return (pos_targets, neg_intervals).

    pos_targets: list of dicts {start,end,kind,match_type} for recall + precision.
      kind in {"span","enum"}.
    neg_intervals: list of (start,end).
    """
    pos, neg = [], []
    for s in article.get("spans", []):
        pos.append({"start": s["start"], "end": s["end"], "kind": "span",
                    "match_type": s["match_type"], "text": s["text"]})
    for e in article.get("shared_head_enumerations", []):
        # enumeration phrase; its parts carry match_types — record the phrase and
        # the set of part match_types for coarse recall.
        mtypes = sorted({p["match_type"] for p in e.get("pathways", [])})
        pos.append({"start": e["start"], "end": e["end"], "kind": "enum",
                    "match_type": "+".join(mtypes), "text": e["text"]})
    for n in article.get("metabolites_not_pathways", []):
        neg.append((n["start"], n["end"]))
    for n in article.get("out_of_vocab_pathways", []):
        neg.append((n["start"], n["end"]))
    return pos, neg


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--vocab", action="store_true",
                    help="include the 98 Recon names in the prompt")
    ap.add_argument("--strict", action="store_true",
                    help="use the strict compound-name rule (default: lenient, the "
                         "chosen Phase 3 config)")
    ap.add_argument("--booster", action="store_true",
                    help="merge in deterministic booster spans (llm/booster.py)")
    ap.add_argument("--report", default=None, help="optional JSON report path")
    args = ap.parse_args()

    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    vocab = json.loads(VOCAB_FILE.read_text(encoding="utf-8")) if args.vocab else None
    query_map = load_query_pathways()

    tot_tp = tot_fp = tot_unl = 0
    recall_hit: dict[str, int] = {}
    recall_tot: dict[str, int] = {}
    report = []

    variant = ("with-vocab" if args.vocab else "no-vocab") + \
        ("+strict" if args.strict else "+lenient") + \
        ("+booster" if args.booster else "")
    print(f"Model: {args.model}   Prompt: {variant}\n" + "=" * 64)

    for art in gold["articles"]:
        pmid = art["pmid"]
        text = art["abstract"]
        qps = query_map.get(pmid, [])
        pos, neg = gold_intervals(art)

        mentions = extract_guided(text, qps, vocab=vocab, model=args.model,
                                  lenient=not args.strict)
        if args.booster:
            mentions = merge(mentions, boost(text))

        # precision classification
        tp = fp = unl = 0
        detail = []
        for m in mentions:
            mi = (m["start"], m["end"])
            hit_pos = any(overlaps(mi, (p["start"], p["end"])) for p in pos)
            hit_neg = any(overlaps(mi, n) for n in neg)
            if hit_pos:
                cls = "TP"; tp += 1
            elif hit_neg:
                cls = "FP_neg"; fp += 1
            else:
                cls = "UNLABELED"; unl += 1
            detail.append({**m, "class": cls})

        # recall per gold target
        r_hit = {}
        for p in pos:
            key = f'{p["kind"]}:{p["match_type"]}'
            recall_tot[key] = recall_tot.get(key, 0) + 1
            covered = any(overlaps((m["start"], m["end"]), (p["start"], p["end"]))
                          for m in mentions)
            if covered:
                recall_hit[key] = recall_hit.get(key, 0) + 1
            r_hit.setdefault(key, [0, 0])
            r_hit[key][1] += 1
            r_hit[key][0] += int(covered)

        tot_tp += tp; tot_fp += fp; tot_unl += unl
        n = len(mentions)
        prec_l = tp / (tp + fp) if (tp + fp) else float("nan")
        print(f"\nPMID {pmid}  ({len(qps)} query pathways) — {n} mentions")
        print(f"  TP={tp}  FP_neg={fp}  UNLABELED={unl}  "
              f"precision(lenient)={prec_l:.2f}")
        for d in detail:
            print(f"    {d['class']:<9} [{d['start']:>4}:{d['end']:<4}] {d['surface']}")
        report.append({"pmid": pmid, "n_mentions": n, "tp": tp, "fp_neg": fp,
                       "unlabeled": unl, "mentions": detail})

    # totals
    n_all = tot_tp + tot_fp + tot_unl
    prec_strict = tot_tp / n_all if n_all else float("nan")
    prec_len = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else float("nan")
    print("\n" + "=" * 64)
    print(f"TOTAL mentions={n_all}  TP={tot_tp}  FP_neg={tot_fp}  UNLABELED={tot_unl}")
    print(f"Precision (strict, unlabeled count against) = {prec_strict:.2f}")
    print(f"Precision (lenient, unlabeled excluded)     = {prec_len:.2f}")
    print("\nRecall by gold target type:")
    for key in sorted(recall_tot):
        h, t = recall_hit.get(key, 0), recall_tot[key]
        print(f"  {key:<28} {h}/{t}  ({h / t:.0%})")

    if args.report:
        Path(args.report).write_text(
            json.dumps({"model": args.model, "variant": variant,
                        "totals": {"n": n_all, "tp": tot_tp, "fp_neg": tot_fp,
                                   "unlabeled": tot_unl,
                                   "precision_strict": prec_strict,
                                   "precision_lenient": prec_len},
                        "recall": {k: [recall_hit.get(k, 0), recall_tot[k]]
                                   for k in recall_tot},
                        "articles": report}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nReport written: {args.report}")


if __name__ == "__main__":
    main()
