#!/usr/bin/env python3
"""
predict_abstracts.py

Run the Run 005 pathway-NER model over the abstracts in
`extracted_disease_pathway_db_disease_pathway_just_abstracts.json` and emit,
per PMID, every pathway span the model detected together with its character
offsets.

The model is a binary B/I/O pathway tagger (it does not classify which of the
98 Recon pathways a span is) — so "detected pathways" here means the surface
text spans it tagged as Pathway, with their [start, end) offsets into the
abstract.

Long abstracts (>512 tokens) are handled with an overlapping sliding window
(stride 64) so no span is lost to truncation.

Inputs:
  - models/pathway-ner-005/                                   (Run 005 model)
  - data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json

Output:
  - playground/model_005_analysis/model_005_abstract_predictions.json

Related:
  - knowledge_base/model_experiments.md   (Run 005 description)
  - playground/exact_match_analysis.md     (the training-label analysis)

Run from repo root:
  <venv>/bin/python3 playground/model_005_analysis/predict_abstracts.py
"""

import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, BertForTokenClassification

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models/pathway-ner-005"
INPUT = ROOT / "data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json"
OUTPUT = ROOT / "playground/model_005_analysis/model_005_abstract_predictions.json"

MAX_LEN = 512
STRIDE = 64
ID2LABEL = {0: "O", 1: "B-Pathway", 2: "I-Pathway"}


def words_from_window(offsets, labels, word_ids):
    """Collapse subword tokens into whole words so a span can never break in
    the middle of a word. Each word takes the predicted label of its FIRST
    subword (matching how training assigned labels; continuations were -100).
    Returns [(char_start, char_end, label_name), ...]."""
    words = []
    prev_wid = None
    for (cs, ce), lab, wid in zip(offsets, labels, word_ids):
        if wid is None:              # special token
            continue
        if wid != prev_wid:          # first subword of a new word
            words.append([cs, ce, ID2LABEL[lab]])
        else:                        # continuation subword — extend char span
            words[-1][1] = ce
        prev_wid = wid
    return words


def spans_from_words(words) -> list[tuple[int, int]]:
    """Reconstruct char spans from word-level labels. A B word opens a span;
    contiguous I words extend it. A lone I (no preceding B) opens a span."""
    spans = []
    cur = None
    for cs, ce, name in words:
        if name == "B-Pathway":
            if cur:
                spans.append(tuple(cur))
            cur = [cs, ce]
        elif name == "I-Pathway":
            if cur:
                cur[1] = ce
            else:
                cur = [cs, ce]
        else:                        # O
            if cur:
                spans.append(tuple(cur))
                cur = None
    if cur:
        spans.append(tuple(cur))
    return spans


def keep_longest(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Drop spans fully contained in another; dedupe; sort by start."""
    uniq = sorted(set(spans), key=lambda s: s[1] - s[0], reverse=True)
    kept: list[tuple[int, int]] = []
    for s in uniq:
        if not any(k[0] <= s[0] and s[1] <= k[1] for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s[0])


@torch.no_grad()
def predict(text, tokenizer, model, device) -> list[dict]:
    if not text.strip():
        return []
    enc = tokenizer(
        text,
        max_length=MAX_LEN,
        truncation=True,
        stride=STRIDE,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        return_tensors="pt",
        padding=True,
    )
    offset_batches = enc["offset_mapping"].tolist()
    n_windows = enc["input_ids"].shape[0]
    word_id_batches = [enc.word_ids(i) for i in range(n_windows)]

    model_inputs = {
        "input_ids": enc["input_ids"].to(device),
        "attention_mask": enc["attention_mask"].to(device),
    }
    logits = model(**model_inputs).logits
    preds = logits.argmax(-1).tolist()

    all_spans: list[tuple[int, int]] = []
    for offsets, labels, word_ids in zip(offset_batches, preds, word_id_batches):
        words = words_from_window(offsets, labels, word_ids)
        all_spans.extend(spans_from_words(words))

    spans = keep_longest(all_spans)
    return [{"start": s, "end": e, "text": text[s:e]} for s, e in spans]


def main() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print(f"Loading model: {MODEL_DIR}")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = BertForTokenClassification.from_pretrained(str(MODEL_DIR)).to(device).eval()

    records = json.loads(INPUT.read_text(encoding="utf-8"))
    print(f"Records: {len(records)}")

    out = []
    total_spans = 0
    for i, r in enumerate(records):
        abstract = r.get("abstract") or ""
        detected = predict(abstract, tokenizer, model, device)
        total_spans += len(detected)
        out.append({
            "pmid": r.get("pmid"),
            "disease": r.get("disease"),
            "expected_pathway": r.get("pathway"),
            "num_detected": len(detected),
            "detected_pathways": detected,
        })
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(records)} processed")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    with_spans = sum(1 for r in out if r["num_detected"] > 0)
    print("─" * 60)
    print(f"Total records      : {len(out)}")
    print(f"Records with spans : {with_spans}")
    print(f"Total spans        : {total_spans}")
    print(f"Output             : {OUTPUT}")


if __name__ == "__main__":
    main()
