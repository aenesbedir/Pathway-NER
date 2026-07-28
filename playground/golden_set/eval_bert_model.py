#!/usr/bin/env python3
"""
eval_bert_model.py

Evaluate a fine-tuned BiomedBERT token-classification checkpoint on the golden
set — the same 10 hand-curated abstracts, scored with the **same methodology** as
`eval_llm_guided.py`, so the student model can be compared directly against the
guided-LLM numbers in `data/silver/eval_qwen*.json`.

Scoring (offset-based, identical to eval_llm_guided.py):
  - POS gold intervals  = every `spans` entry + every `shared_head_enumerations`
    phrase (real pathway mentions).
  - NEG gold intervals  = `metabolites_not_pathways` + `out_of_vocab_pathways`
    (must NOT be tagged).
Each predicted span is classified by interval overlap:
  - TP        : overlaps a POS interval
  - FP_neg    : overlaps a NEG interval (and no POS) — a real precision error
  - UNLABELED : overlaps neither — either a pathway we didn't annotate, or an FP;
                reported, not auto-judged.

Recall is reported per gold target type (`span:<match_type>`, `enum:<types>`).

Predictions come from BIO decoding over the fast tokenizer's `offset_mapping`;
`I-Pathway` without a preceding `B-Pathway` opens a new span (lenient decode).

Run from repo root:
    /home/enes/sci-usage/venv310/bin/python3 playground/golden_set/eval_bert_model.py \\
        --model-dir models/pathway-ner-gold-008 \\
        --report analysis/golden_set_gold-008.json
"""

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "playground/golden_set/golden_set.json"

MAX_TOKENS = 512
ID2LABEL = {0: "O", 1: "B-Pathway", 2: "I-Pathway"}


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def gold_intervals(article: dict):
    """Return (pos_targets, neg_intervals) — same shape as eval_llm_guided.py."""
    pos, neg = [], []
    for s in article.get("spans", []):
        pos.append({"start": s["start"], "end": s["end"], "kind": "span",
                    "match_type": s["match_type"], "text": s["text"]})
    for e in article.get("shared_head_enumerations", []):
        mtypes = sorted({p["match_type"] for p in e.get("pathways", [])})
        pos.append({"start": e["start"], "end": e["end"], "kind": "enum",
                    "match_type": "+".join(mtypes), "text": e["text"]})
    for n in article.get("metabolites_not_pathways", []):
        neg.append((n["start"], n["end"]))
    for n in article.get("out_of_vocab_pathways", []):
        neg.append((n["start"], n["end"]))
    return pos, neg


def predict_spans(text: str, tokenizer, model, device) -> list[dict]:
    """Run the model and BIO-decode into character spans."""
    enc = tokenizer(text, max_length=MAX_TOKENS, truncation=True,
                    return_offsets_mapping=True, return_tensors="pt")
    offsets = enc.pop("offset_mapping")[0].tolist()
    enc = {k: v.to(device) for k, v in enc.items()}

    with torch.no_grad():
        logits = model(**enc).logits[0]
    pred_ids = logits.argmax(-1).tolist()

    spans, cur = [], None
    for (start, end), pid in zip(offsets, pred_ids):
        if start == end:          # special token
            continue
        label = ID2LABEL.get(pid, "O")
        if label == "B-Pathway":
            if cur:
                spans.append(cur)
            cur = {"start": start, "end": end}
        elif label == "I-Pathway":
            if cur:
                cur["end"] = end   # continue
            else:
                cur = {"start": start, "end": end}   # lenient: I without B
        else:
            if cur:
                spans.append(cur)
                cur = None
    if cur:
        spans.append(cur)

    for s in spans:
        s["surface"] = text[s["start"]:s["end"]]
    return spans


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True,
                    help="fine-tuned checkpoint directory")
    ap.add_argument("--report", default=None, help="optional JSON report path")
    ap.add_argument("--pmids", nargs="+", default=None,
                    help="restrict to these PMIDs (e.g. the v1 5-abstract subset "
                         "the guided-LLM runs were scored on)")
    args = ap.parse_args()

    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if args.pmids:
        keep = set(args.pmids)
        gold["articles"] = [a for a in gold["articles"] if a["pmid"] in keep]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForTokenClassification.from_pretrained(args.model_dir)
    model.to(device).eval()

    name = Path(args.model_dir).name
    print(f"Model: {name}   Device: {device}\n" + "=" * 64)

    tot_tp = tot_fp = tot_unl = 0
    recall_hit: dict[str, int] = {}
    recall_tot: dict[str, int] = {}
    report = []

    for art in gold["articles"]:
        pmid, text = art["pmid"], art["abstract"]
        pos, neg = gold_intervals(art)
        mentions = predict_spans(text, tokenizer, model, device)

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

        for p in pos:
            key = f'{p["kind"]}:{p["match_type"]}'
            recall_tot[key] = recall_tot.get(key, 0) + 1
            covered = any(overlaps((m["start"], m["end"]), (p["start"], p["end"]))
                          for m in mentions)
            if covered:
                recall_hit[key] = recall_hit.get(key, 0) + 1

        tot_tp += tp; tot_fp += fp; tot_unl += unl
        n = len(mentions)
        prec_l = tp / (tp + fp) if (tp + fp) else float("nan")
        print(f"\nPMID {pmid} — {n} mentions")
        print(f"  TP={tp}  FP_neg={fp}  UNLABELED={unl}  "
              f"precision(lenient)={prec_l:.2f}")
        for d in detail:
            print(f"    {d['class']:<9} [{d['start']:>4}:{d['end']:<4}] {d['surface']}")
        report.append({"pmid": pmid, "n_mentions": n, "tp": tp, "fp_neg": fp,
                       "unlabeled": unl, "mentions": detail})

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
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"model": name, "model_dir": args.model_dir, "variant": "bert-finetuned",
             "totals": {"n": n_all, "tp": tot_tp, "fp_neg": tot_fp,
                        "unlabeled": tot_unl,
                        "precision_strict": prec_strict,
                        "precision_lenient": prec_len},
             "recall": {k: [recall_hit.get(k, 0), recall_tot[k]] for k in recall_tot},
             "articles": report}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nReport written: {out}")


if __name__ == "__main__":
    main()
