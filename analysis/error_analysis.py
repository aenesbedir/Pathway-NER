#!/usr/bin/env python3
"""
error_analysis.py

Runs Run 001 model on the test set and saves:
  - All predictions with true labels, decoded tokens, and span strings + char offsets
  - False positives: model predicted pathway, label says O
  - False negatives: label says pathway, model predicted O
  - True positives: correctly predicted pathway spans
  - nervaluate-ready section for entity-level evaluation

Output: analysis/error_analysis.json

Run with:
    python3 analysis/error_analysis.py
"""

import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, BertForTokenClassification
from nervaluate import Evaluator

MODEL_DIR = Path("models/pathway-ner")
TEST_FILE = Path("data/processed/test.jsonl")
ABSTRACTS_FILE = Path("data/raw/abstracts.jsonl")
DB_FILE = Path("data/processed/db_with_extracted_pathways.json")
OUTPUT = Path("analysis/error_analysis.json")

ID2LABEL = {0: "O", 1: "B-Pathway", 2: "I-Pathway"}
MAX_TOKENS = 512


def load_texts() -> dict:
    texts = {}
    for line in ABSTRACTS_FILE.open(encoding="utf-8"):
        r = json.loads(line)
        texts[str(r["pmid"])] = {
            "abstract": r.get("abstract", ""),
            "full_text": r.get("full_text", ""),
        }
    db = json.loads(DB_FILE.read_text(encoding="utf-8"))
    for r in db:
        pmid = str(r["pmid"])
        if pmid not in texts:
            texts[pmid] = {
                "abstract": r.get("abstract", ""),
                "full_text": "",
            }
    return texts


def get_source_and_offsets(tokenizer, rec, texts):
    """Return (source_text, offset_mapping) for a test record by matching input_ids."""
    pmid = str(rec["pmid"])
    record_ids = rec["input_ids"]
    content_ids = record_ids[1:-1]

    entry = texts.get(pmid, {})

    abstract = (entry.get("abstract") or "").strip()
    if abstract:
        enc = tokenizer(
            abstract,
            return_offsets_mapping=True,
            truncation=True,
            max_length=MAX_TOKENS,
        )
        if list(enc["input_ids"])[1:-1] == content_ids:
            return abstract, list(enc["offset_mapping"])

    full_text = (entry.get("full_text") or "").strip()
    if full_text:
        full_enc = tokenizer(
            full_text,
            return_offsets_mapping=True,
            truncation=False,
        )
        full_content = list(full_enc["input_ids"])[1:-1]
        nc = len(content_ids)
        for si in range(len(full_content) - nc + 1):
            if full_content[si : si + nc] == content_ids:
                full_offsets = list(full_enc["offset_mapping"])
                full_labels = [None] + [None] * len(full_content) + [None]
                win_start_char = full_offsets[1 + si][0]
                win_end_char = full_offsets[si + nc][1]
                window_text = full_text[win_start_char:win_end_char]
                win_enc = tokenizer(
                    window_text,
                    return_offsets_mapping=True,
                    truncation=True,
                    max_length=MAX_TOKENS,
                )
                if list(win_enc["input_ids"])[1:-1] == content_ids:
                    return window_text, list(win_enc["offset_mapping"])
                # Fallback: use offsets shifted to window-relative coords
                shifted = [
                    (off[0] - win_start_char, off[1] - win_start_char)
                    for off in full_offsets[1 + si : 1 + si + nc]
                ]
                full_record_offsets = [(0, 0)] + shifted + [(0, 0)]
                return window_text, full_record_offsets

    return abstract, None


def get_word_end(pos, all_true_labels, offset_mapping):
    """Return the char end of the last subword for the word at `pos`."""
    end = offset_mapping[pos][1]
    j = pos + 1
    while j < len(all_true_labels):
        if all_true_labels[j] != -100:
            break
        off = offset_mapping[j]
        if off == (0, 0) or off == [0, 0]:
            break
        end = off[1]
        j += 1
    return end


def merge_adjacent_spans(spans, gap=2):
    """Merge spans that are within `gap` characters of each other."""
    if not spans:
        return spans
    sorted_spans = sorted(spans, key=lambda x: x["start"])
    merged = [dict(sorted_spans[0])]
    for span in sorted_spans[1:]:
        prev = merged[-1]
        if span["start"] != -1 and prev["end"] != -1 and span["start"] - prev["end"] <= gap:
            prev["end"] = span["end"]
            prev["text"] = prev["text"] + " " + span["text"]
        else:
            merged.append(dict(span))
    return merged


def extract_spans_with_offsets(all_tokens, all_pred_labels, all_true_labels, offset_mapping, tokenizer, source_text):
    """Extract (pred_spans, true_spans) with char offsets from the full token sequence."""

    def _extract(label_seq):
        active = [
            (pos, tok, lbl)
            for pos, (tok, lbl) in enumerate(zip(all_tokens, label_seq))
            if all_true_labels[pos] != -100
        ]
        spans = []
        j = 0
        while j < len(active):
            pos, tok, lbl = active[j]
            if lbl == 1:
                span_tokens = [tok]
                char_start = offset_mapping[pos][0]
                last_pos = pos
                k = j + 1
                while k < len(active) and active[k][2] == 2:
                    span_tokens.append(active[k][1])
                    last_pos = active[k][0]
                    k += 1
                char_end = get_word_end(last_pos, all_true_labels, offset_mapping)
                # Slice source text directly to avoid tokenizer decoding artifacts
                if source_text and char_start >= 0 and char_end > char_start:
                    text = source_text[char_start:char_end]
                else:
                    text = tokenizer.convert_tokens_to_string(span_tokens).strip()
                spans.append({"text": text, "start": char_start, "end": char_end})
                j = k
            else:
                j += 1
        return spans

    return _extract(all_pred_labels), _extract(all_true_labels)


def main():
    print("Loading model and tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    model = BertForTokenClassification.from_pretrained(str(MODEL_DIR))
    model.eval()

    texts = load_texts()
    test_records = [json.loads(l) for l in TEST_FILE.open(encoding="utf-8")]
    print(f"Test records: {len(test_records)}")

    results = []
    summary = {"true_positives": [], "partial_true_positives": [], "false_positives": [], "false_negatives": []}
    nervaluate_true = []
    nervaluate_pred = []

    no_offsets_count = 0

    for rec in test_records:
        input_ids = torch.tensor([rec["input_ids"]])
        attention_mask = torch.tensor([rec["attention_mask"]])
        true_labels = rec["labels"]

        with torch.no_grad():
            logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
        pred_labels = logits[0].argmax(dim=-1).tolist()

        tokens = tokenizer.convert_ids_to_tokens(rec["input_ids"])

        source_text, offset_mapping = get_source_and_offsets(tokenizer, rec, texts)

        if offset_mapping is not None:
            pred_spans, true_spans = extract_spans_with_offsets(
                tokens, pred_labels, true_labels, offset_mapping, tokenizer, source_text
            )
        else:
            no_offsets_count += 1
            active = [
                (tok, pred, true)
                for tok, pred, true in zip(tokens, pred_labels, true_labels)
                if true != -100
            ]
            active_tokens = [x[0] for x in active]
            active_preds = [x[1] for x in active]
            active_trues = [x[2] for x in active]

            def _extract_plain(toks, labs):
                spans = []
                i = 0
                while i < len(toks):
                    if labs[i] in (1, 2):
                        span_toks = [toks[i]]
                        j = i + 1
                        while j < len(toks) and labs[j] == 2:
                            span_toks.append(toks[j])
                            j += 1
                        text = tokenizer.convert_tokens_to_string(span_toks).strip()
                        spans.append({"text": text, "start": -1, "end": -1})
                        i = j
                    else:
                        i += 1
                return spans

            pred_spans = _extract_plain(active_tokens, active_preds)
            true_spans = _extract_plain(active_tokens, active_trues)

        pred_spans = merge_adjacent_spans(pred_spans)

        pred_texts = [s["text"].lower() for s in pred_spans]
        true_texts = [s["text"].lower() for s in true_spans]

        def overlaps(a, b):
            if a["start"] == -1 or b["start"] == -1:
                return False
            inter_start = max(a["start"], b["start"])
            inter_end = min(a["end"], b["end"])
            if inter_end <= inter_start:
                return False
            intersection = inter_end - inter_start
            pred_len = a["end"] - a["start"]
            # Overlap must cover at least 50% of the predicted span
            return pred_len > 0 and intersection / pred_len >= 0.5

        tp_spans = [s for s in pred_spans if s["text"].lower() in true_texts]
        partial_tp_spans = [
            {"pred": p, "true": t}
            for p in pred_spans if p["text"].lower() not in true_texts
            for t in true_spans if overlaps(p, t) and t["text"].lower() not in pred_texts
        ]
        partial_pred_texts = {item["pred"]["text"].lower() for item in partial_tp_spans}
        partial_true_texts = {item["true"]["text"].lower() for item in partial_tp_spans}
        fp_spans = [s for s in pred_spans if s["text"].lower() not in true_texts and s["text"].lower() not in partial_pred_texts]
        fn_spans = [s for s in true_spans if s["text"].lower() not in pred_texts and s["text"].lower() not in partial_true_texts]

        record_result = {
            "pmid": rec["pmid"],
            "pathway_ids": rec["pathway_ids"],
            "abstract": (texts.get(str(rec["pmid"]), {}).get("abstract") or "")[:500],
            "true_spans": true_spans,
            "pred_spans": pred_spans,
            "true_positives": tp_spans,
            "partial_true_positives": partial_tp_spans,
            "false_positives": fp_spans,
            "false_negatives": fn_spans,
        }
        results.append(record_result)

        for s in tp_spans:
            summary["true_positives"].append({"span": s, "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})
        for item in partial_tp_spans:
            summary["partial_true_positives"].append({"pred": item["pred"], "true": item["true"], "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})
        for s in fp_spans:
            summary["false_positives"].append({"span": s, "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})
        for s in fn_spans:
            summary["false_negatives"].append({"span": s, "pmid": rec["pmid"], "pathway_ids": rec["pathway_ids"]})

        nervaluate_true.append([
            {"label": "Pathway", "start": s["start"], "end": s["end"]}
            for s in true_spans
        ])
        nervaluate_pred.append([
            {"label": "Pathway", "start": s["start"], "end": s["end"]}
            for s in pred_spans
        ])

    if no_offsets_count:
        print(f"Warning: {no_offsets_count} records had no offset mapping (spans have start=-1, end=-1)")

    output = {
        "summary": summary,
        "per_record": results,
        "nervaluate": {
            "true_named_entities": nervaluate_true,
            "pred_named_entities": nervaluate_pred,
        },
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    tp = len(summary["true_positives"])
    ptp = len(summary["partial_true_positives"])
    fp = len(summary["false_positives"])
    fn = len(summary["false_negatives"])
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"\n{'─'*60}")
    print(f"True positives         : {tp}")
    print(f"Partial true positives : {ptp}  (overlap but wrong boundaries)")
    print(f"False positives        : {fp}")
    print(f"False negatives        : {fn}")
    print(f"Span-level P           : {precision:.4f}")
    print(f"Span-level R           : {recall:.4f}")
    print(f"Span-level F1          : {f1:.4f}")
    print(f"{'─'*60}")
    print(f"\n=== PARTIAL TRUE POSITIVES (overlap, wrong boundaries) ===")
    for item in summary["partial_true_positives"]:
        print(f"  pred: '{item['pred']['text']}' [{item['pred']['start']}:{item['pred']['end']}]")
        print(f"  true: '{item['true']['text']}' [{item['true']['start']}:{item['true']['end']}]")
        print()
    print(f"\n=== FALSE POSITIVES (model predicted, label=O) ===")
    for fp_item in summary["false_positives"]:
        print(f"  '{fp_item['span']['text']}' [{fp_item['span']['start']}:{fp_item['span']['end']}] — {fp_item['pathway_ids']}")
    print(f"\n=== FALSE NEGATIVES (label=pathway, model missed) ===")
    for fn_item in summary["false_negatives"]:
        print(f"  '{fn_item['span']['text']}' [{fn_item['span']['start']}:{fn_item['span']['end']}] — {fn_item['pathway_ids']}")
    print(f"\nFull output saved to {OUTPUT}")

    # nervaluate: strict / exact / partial / type scores
    true_ne = [
        [{"label": s["label"], "start": s["start"], "end": s["end"]}
         for s in rec if s["start"] != -1]
        for rec in nervaluate_true
    ]
    pred_ne = [
        [{"label": s["label"], "start": s["start"], "end": s["end"]}
         for s in rec if s["start"] != -1]
        for rec in nervaluate_pred
    ]
    evaluator = Evaluator(true_ne, pred_ne, tags=["Pathway"])
    results_nv, results_agg, *_ = evaluator.evaluate()
    print(f"\n{'─'*60}")
    print(f"{'':20s}  {'P':>6}  {'R':>6}  {'F1':>6}")
    for scheme in ("strict", "exact", "partial", "ent_type"):
        m = results_nv[scheme]
        p = m["precision"]
        r = m["recall"]
        f = m["f1"]
        print(f"  {scheme:<18}  {p:>6.4f}  {r:>6.4f}  {f:>6.4f}")
    print(f"{'─'*60}")


if __name__ == "__main__":
    main()
