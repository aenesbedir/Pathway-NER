#!/usr/bin/env python3
"""
error_analysis.py

Runs Run 001 model on the test set and saves:
  - All predictions with true labels, decoded tokens, and span strings
  - False positives: model predicted pathway, label says O
  - False negatives: label says pathway, model predicted O
  - True positives: correctly predicted pathway spans

Output: analysis/error_analysis.json

Run with:
    python3 analysis/error_analysis.py
"""

import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, BertForTokenClassification

MODEL_DIR = Path("models/pathway-ner")
TEST_FILE = Path("data/processed/test.jsonl")
ABSTRACTS_FILE = Path("data/raw/abstracts.jsonl")
DB_FILE = Path("data/processed/db_with_extracted_pathways.json")
OUTPUT = Path("analysis/error_analysis.json")

ID2LABEL = {0: "O", 1: "B-Pathway", 2: "I-Pathway"}


def load_texts() -> dict:
    texts = {}
    for line in ABSTRACTS_FILE.open(encoding="utf-8"):
        r = json.loads(line)
        texts[r["pmid"]] = r.get("abstract", "")
    db = json.loads(DB_FILE.read_text(encoding="utf-8"))
    for r in db:
        pmid = str(r["pmid"])
        if pmid not in texts:
            texts[pmid] = r.get("abstract", "")
    return texts


def extract_spans(tokens, labels, tokenizer):
    """Extract readable span strings from a token+label sequence."""
    spans = []
    i = 0
    while i < len(tokens):
        if labels[i] in (1, 2):
            span_tokens = [tokens[i]]
            j = i + 1
            while j < len(tokens) and labels[j] == 2:
                span_tokens.append(tokens[j])
                j += 1
            span = tokenizer.convert_tokens_to_string(span_tokens).strip()
            spans.append(span)
            i = j
        else:
            i += 1
    return spans


def main():
    print("Loading model and tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = BertForTokenClassification.from_pretrained(str(MODEL_DIR))
    model.eval()

    texts = load_texts()
    test_records = [json.loads(l) for l in TEST_FILE.open(encoding="utf-8")]
    print(f"Test records: {len(test_records)}")

    results = []
    summary = {"true_positives": [], "false_positives": [], "false_negatives": []}

    for rec in test_records:
        input_ids = torch.tensor([rec["input_ids"]])
        attention_mask = torch.tensor([rec["attention_mask"]])
        true_labels = rec["labels"]

        with torch.no_grad():
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
        pred_labels = logits[0].argmax(dim=-1).tolist()

        tokens = tokenizer.convert_ids_to_tokens(rec["input_ids"])

        # Filter out -100 positions
        active = [(tok, pred, true)
                  for tok, pred, true in zip(tokens, pred_labels, true_labels)
                  if true != -100]
        active_tokens = [x[0] for x in active]
        active_preds  = [x[1] for x in active]
        active_trues  = [x[2] for x in active]

        pred_spans = extract_spans(active_tokens, active_preds, tokenizer)
        true_spans = extract_spans(active_tokens, active_trues, tokenizer)

        tp_spans = [s for s in pred_spans if s.lower() in [t.lower() for t in true_spans]]
        fp_spans = [s for s in pred_spans if s.lower() not in [t.lower() for t in true_spans]]
        fn_spans = [s for s in true_spans if s.lower() not in [t.lower() for t in pred_spans]]

        record_result = {
            "pmid": rec["pmid"],
            "pathway_ids": rec["pathway_ids"],
            "abstract": texts.get(rec["pmid"], "")[:500],
            "true_spans": true_spans,
            "pred_spans": pred_spans,
            "true_positives": tp_spans,
            "false_positives": fp_spans,
            "false_negatives": fn_spans,
        }
        results.append(record_result)

        for s in tp_spans:
            summary["true_positives"].append({"span": s, "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})
        for s in fp_spans:
            summary["false_positives"].append({"span": s, "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})
        for s in fn_spans:
            summary["false_negatives"].append({"span": s, "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})

    # Save full output
    output = {"summary": summary, "per_record": results}
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    tp = len(summary["true_positives"])
    fp = len(summary["false_positives"])
    fn = len(summary["false_negatives"])
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n{'─'*60}")
    print(f"True positives  : {tp}")
    print(f"False positives : {fp}")
    print(f"False negatives : {fn}")
    print(f"Span-level P    : {precision:.4f}")
    print(f"Span-level R    : {recall:.4f}")
    print(f"Span-level F1   : {f1:.4f}")
    print(f"{'─'*60}")
    print(f"\n=== FALSE POSITIVES (model predicted, label=O) ===")
    for fp_item in summary["false_positives"]:
        print(f"  '{fp_item['span']}' — {fp_item['pathway_ids']}")
    print(f"\n=== FALSE NEGATIVES (label=pathway, model missed) ===")
    for fn_item in summary["false_negatives"]:
        print(f"  '{fn_item['span']}' — {fn_item['pathway_ids']}")
    print(f"\nFull output saved to {OUTPUT}")


if __name__ == "__main__":
    main()
