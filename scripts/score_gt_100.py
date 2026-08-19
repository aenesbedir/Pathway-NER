#!/usr/bin/env python3
"""Score the pathway-ner-gold-wave4-* checkpoints against the human-reviewed
gt_100 ground truth (doccano/golden dataset/gt_100.jsonl).

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

Metrics (per model, on the 100 gt_100 abstracts):
  * seqeval entity F1 / P / R — the identical convention used in train.py and
    stored in each run's test_results.json. Span matching is token-run based,
    so it is tokenizer-agnostic (char-offset exact matching is NOT used: the
    ModernBERT tokenizer emits word offsets that include a leading space, so
    its spans can never equal human character offsets exactly).
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
    true_tags, pred_tags = [], []
    for i, wid in enumerate(word_ids):
        if wid is None or wid == prev:
            continue
        prev = wid
        s, e = offsets[i]
        true_tags.append(ID2LABEL[label_for_token(s, e, spans)])
        pred_tags.append(ID2LABEL[int(pred_ids[i])])
    return true_tags, pred_tags


def score_model(model_dir: Path, gt: list[dict], max_tokens: int, device) -> dict:
    mp = model_path(model_dir)
    tokenizer = AutoTokenizer.from_pretrained(str(mp))
    model = AutoModelForTokenClassification.from_pretrained(str(mp)).to(device)
    model.eval()

    seq_true, seq_pred = [], []
    n_gold = 0
    for rec in gt:
        text = rec["text"]
        spans = [(e["start_offset"], e["end_offset"]) for e in rec["entities"]
                 if e["label"] == "PATHWAY"]
        n_gold += len(spans)
        true_tags, pred_tags = predict_sequence(
            model, tokenizer, text, spans, max_tokens, device)
        seq_true.append(true_tags)
        seq_pred.append(pred_tags)

    return {
        "model": model_dir.name,
        "max_tokens": max_tokens,
        "seqeval": {
            "f1": round(seq_f1(seq_true, seq_pred), 4),
            "precision": round(seq_precision(seq_true, seq_pred), 4),
            "recall": round(seq_recall(seq_true, seq_pred), 4),
        },
        "n_gold_pathway_spans": n_gold,
        "n_docs": len(gt),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="doccano/golden dataset/gt_100.jsonl")
    ap.add_argument("--model-dir", action="append", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    gt = load_gt(Path(args.gt))
    for md in args.model_dir:
        res = score_model(Path(md), gt, args.max_tokens, args.device)
        print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
