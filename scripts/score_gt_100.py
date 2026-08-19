#!/usr/bin/env python3
"""Score the pathway-ner-gold-wave4-* / runs-truba-checkpoints checkpoints
against the human-reviewed gt_100 ground truth
(doccano/golden dataset/gt_100.jsonl).

Only PATHWAY spans in gt_100 are used. The models are single-label pathway NER
(LABEL2ID = {O, B-Pathway, I-Pathway}); DISEASE spans are treated as
background for this task.

Labels follow the exact scheme of preprocessing/tag_bio.py:
  * tokenize(text, max_length=<model ctx>, truncation=True,
    return_offsets_mapping=True)
  * only the FIRST wordpiece of each word is scored — subsequent pieces and
    special tokens are -100 (ignored), exactly like the training data
  * B if the token's char span contains a gold span start, I if it overlaps a
    gold span (but does not contain its start), else O

Metrics (per model, on the 100 gt_100 abstracts), reported side by side:
  * seqeval entity F1 / P / R — the identical convention used in train.py and
    stored in each run's test_results.json. Span matching is token-run based,
    so it is tokenizer-agnostic (char-offset exact matching is NOT used: the
    ModernBERT tokenizer emits word offsets that include a leading space, so
    its spans can never equal human character offsets exactly).
  * partial (only when --partial <t> is given) — gold-coverage matching:
    a predicted span counts toward a gold span when it covers >= t of the
    gold's characters (|pred & gold| / |gold| >= t). Pairs are matched greedily
    one-to-one by descending coverage so no gold or prediction is double
    counted. Reported as a separate, clearly-labelled metric; it never
    replaces seqeval.
"""

import argparse
import json
import sys
from pathlib import Path

import torch
from seqeval.metrics import f1_score as seq_f1
from seqeval.metrics import precision_score as seq_precision
from seqeval.metrics import recall_score as seq_recall
from transformers import AutoModelForTokenClassification, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preprocessing.tag_bio import label_for_token  # noqa: E402

LABEL2ID = {"O": 0, "B-Pathway": 1, "I-Pathway": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}


def load_gt(path: Path) -> list[dict]:
    """admin.jsonl records: {id, text, meta:{pmid}, entities:[...]}."""
    return [json.loads(l) for l in path.open(encoding="utf-8")]


def model_path(dir_: Path) -> Path:
    """Resolve the checkpoint directory: top-level model or nested checkpoint-*."""
    if (dir_ / "model.safetensors").exists():
        return dir_
    cps = sorted(dir_.glob("checkpoint-*"))
    if cps:
        return cps[-1]
    raise SystemExit(f"no model.safetensors or checkpoint-* under {dir_}")


def decode_spans(tags, offsets):
    """Decode a B..I token sequence into (start, end) character spans."""
    spans = []
    cur = None
    for tag, (s, e) in zip(tags, offsets):
        if tag == "B-Pathway":
            if cur is not None:
                spans.append(tuple(cur))
            cur = [s, e]
        elif tag == "I-Pathway":
            if cur is None:
                cur = [s, e]  # stray I: start a span
            else:
                cur[1] = e
        else:  # O
            if cur is not None:
                spans.append(tuple(cur))
                cur = None
    if cur is not None:
        spans.append(tuple(cur))
    return spans


def partial_confusion(gold_spans, pred_spans, threshold):
    """Greedy one-to-one gold-coverage matching.

    A pred covers a gold iff the fraction of gold's characters inside pred is
    >= threshold. Candidate pairs are taken in descending coverage order, each
    gold and pred used once. Returns (tp, fp, fn).
    """
    candidates = []
    for g in gold_spans:
        glen = max(1, g[1] - g[0])
        for p in pred_spans:
            inter = max(0, min(g[1], p[1]) - max(g[0], p[0]))
            if inter / glen >= threshold:
                candidates.append((inter / glen, g, p))
    candidates.sort(reverse=True, key=lambda c: c[0])
    used_gold, used_pred = set(), set()
    tp = 0
    for _, g, p in candidates:
        if g in used_gold or p in used_pred:
            continue
        used_gold.add(g)
        used_pred.add(p)
        tp += 1
    fp = len(pred_spans) - len(used_pred)
    fn = len(gold_spans) - len(used_gold)
    return tp, fp, fn


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


@torch.no_grad()
def predict_sequence(model, tokenizer, text, spans, max_tokens, device):
    enc = tokenizer(
        text,
        max_length=max_tokens,
        truncation=True,
        return_offsets_mapping=True,
        return_attention_mask=True,
    )
    input_ids = torch.tensor([enc["input_ids"]], device=device)
    attn = torch.tensor([enc["attention_mask"]], device=device)
    logits = model(input_ids=input_ids, attention_mask=attn).logits[0]
    pred_ids = logits.argmax(dim=-1).cpu().numpy()

    word_ids = enc.word_ids()
    offsets = enc["offset_mapping"]
    # Keep only the first wordpiece of each word (the positions training scored);
    # gold spans fully beyond the truncation window are naturally absent here.
    prev = None
    true_tags, pred_tags, tok_offsets = [], [], []
    for i, wid in enumerate(word_ids):
        if wid is None or wid == prev:
            continue
        prev = wid
        s, e = offsets[i]
        true_tags.append(ID2LABEL[label_for_token(s, e, spans)])
        pred_tags.append(ID2LABEL[int(pred_ids[i])])
        tok_offsets.append((s, e))
    return true_tags, pred_tags, tok_offsets


def score_model(model_dir: Path, gt: list[dict], max_tokens: int, device,
                partial_threshold: float | None) -> dict:
    mp = model_path(model_dir)
    tokenizer = AutoTokenizer.from_pretrained(str(mp))
    model = AutoModelForTokenClassification.from_pretrained(str(mp)).to(device)
    model.eval()

    seq_true, seq_pred = [], []
    n_gold = 0
    ptp = pfp = pfn = 0
    for rec in gt:
        text = rec["text"]
        spans = [(e["start_offset"], e["end_offset"]) for e in rec["entities"]
                 if e["label"] == "PATHWAY"]
        n_gold += len(spans)
        true_tags, pred_tags, tok_offsets = predict_sequence(
            model, tokenizer, text, spans, max_tokens, device)
        seq_true.append(true_tags)
        seq_pred.append(pred_tags)
        if partial_threshold is not None:
            pred_spans = decode_spans(pred_tags, tok_offsets)
            t, f_pos, f_neg = partial_confusion(spans, pred_spans, partial_threshold)
            ptp += t
            pfp += f_pos
            pfn += f_neg

    res = {
        "model": str(model_dir),
        "max_tokens": max_tokens,
        "seqeval": {
            "f1": round(seq_f1(seq_true, seq_pred), 4),
            "precision": round(seq_precision(seq_true, seq_pred), 4),
            "recall": round(seq_recall(seq_true, seq_pred), 4),
        },
        "n_gold_pathway_spans": n_gold,
        "n_docs": len(gt),
    }
    if partial_threshold is not None:
        p, r, f = prf(ptp, pfp, pfn)
        res["partial"] = {
            "threshold": partial_threshold,
            "f1": f,
            "precision": p,
            "recall": r,
        }
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="doccano/golden dataset/gt_100.jsonl")
    ap.add_argument("--model-dir", action="append", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--partial", type=float, default=None,
                    help="also report gold-coverage partial F1 at this threshold (e.g. 0.5)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    gt = load_gt(Path(args.gt))
    for md in args.model_dir:
        res = score_model(Path(md), gt, args.max_tokens, args.device, args.partial)
        print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
