#!/usr/bin/env python3
"""
train_relation.py

Fine-tune an encoder to classify a (pathway, disease) pair into the v4 label set.

FEASIBILITY PROBE. The question is whether the silver corpus can train a student
at all, not how well. Nothing here writes to `runs/summary.jsonl`: that file is
the record of the NER grid, and a probe whose scores nobody intends to defend
does not belong in it.

Task shape
----------
One example is one pair, not one abstract, matching the annotation unit in
`schema.py`. The abstract is fed whole with every mention of that pair wrapped in
the same `[[PATHWAY]]` / `[[DISEASE]]` markers the teacher saw, so the student is
asked the question the labels answer. Other entities are left unmarked.

Markers are plain text rather than added tokens on purpose: adding tokens means
resizing the embedding matrix, which changes what "the same base model" means
across the grid and costs a warm-up the probe cannot afford to tune.

Truncation
----------
5.6% of these abstracts exceed 512 tokens, and a naive tail-truncation can cut
away the very mentions being asked about - producing an example whose label is
unanswerable from its input. So an over-long abstract is cropped to a character
window centred on the marked spans instead, and the crop is counted.

Splits
------
Train and validation come from the silver corpus, split by PMID so no abstract
appears on both sides. Test is the gt_100 panel, which shares no PMID with the
silver sample (verified: 0 of 79). It is a held-out panel of teacher labels, not
human gold, so a score against it measures agreement with the teacher.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import encoders  # noqa: E402

from schema import LABELS, read_jsonl  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TRAIN = REPO / "data/processed/relation/silver_2k_full/relations_llm_opus48_same_sentence.jsonl"
DEFAULT_TRAIN_CANDS = REPO / "data/processed/relation/silver_2k_full/candidates_same_sentence.jsonl"
DEFAULT_TEST = REPO / (
    "data/processed/gt_100/"
    "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable_v4d_single.jsonl"
)
DEFAULT_TEST_CANDS = REPO / "data/processed/gt_100/candidates_v4.jsonl"
DEFAULT_OUT = REPO / "models_re/relation_ft"

LABEL2ID = {l: i for i, l in enumerate(LABELS)}
MARK = {"PATHWAY": ("[[PATHWAY]]", "[[/PATHWAY]]"), "DISEASE": ("[[DISEASE]]", "[[/DISEASE]]")}


def mark(abstract: str, pathway_spans, disease_spans) -> tuple[str, int, int]:
    """Insert markers around every mention. Returns text and the marked extent."""
    spans = sorted(
        [(s, e, "PATHWAY") for s, e in pathway_spans] + [(s, e, "DISEASE") for s, e in disease_spans]
    )
    out, cur, lo, hi = [], 0, len(abstract), 0
    for s, e, kind in spans:
        if s < cur:  # nested or overlapping mention: the first one wins
            continue
        open_t, close_t = MARK[kind]
        out.append(abstract[cur:s])
        out.append(open_t + abstract[s:e] + close_t)
        cur = e
        lo, hi = min(lo, s), max(hi, e)
    out.append(abstract[cur:])
    text = "".join(out)
    # Shift the extent by the markers inserted before it.
    return text, lo, hi


def crop(text: str, lo: int, hi: int, budget_chars: int) -> str:
    """Crop to a window that still contains the marked region."""
    if len(text) <= budget_chars:
        return text
    span = hi - lo
    slack = max(budget_chars - span, 0) // 2
    start = max(0, lo - slack)
    return text[start : start + budget_chars]


def build(relations: Path, candidates: Path, tokenizer, max_len: int):
    """Pair rows with their abstracts and render the model's input text."""
    cands = {c["candidate_id"]: c for c in read_jsonl(candidates)}
    rows, cropped, missing = [], 0, 0
    # ~4 characters per token is the usual ratio for this tokenizer on abstracts;
    # the budget is generous because the tokenizer truncates what survives.
    budget = max_len * 5
    for r in read_jsonl(relations):
        c = cands.get(r["candidate_id"])
        if c is None:
            missing += 1
            continue
        text, lo, hi = mark(
            c["abstract"],
            [(m["start"], m["end"]) for m in c["pathway_mentions"]],
            [(m["start"], m["end"]) for m in c["disease_mentions"]],
        )
        if len(text) > budget:
            text = crop(text, lo, hi, budget)
            cropped += 1
        rows.append({"text": text, "label": LABEL2ID[r["label"]], "pmid": str(c["pmid"])})
    return rows, {"cropped": cropped, "candidate_not_found": missing}


class PairDataset(Dataset):
    def __init__(self, rows, tokenizer, max_len):
        self.enc = tokenizer(
            [r["text"] for r in rows], truncation=True, max_length=max_len, padding=False
        )
        self.labels = [r["label"] for r in rows]

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        item = {k: v[i] for k, v in self.enc.items()}
        item["labels"] = self.labels[i]
        return item


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    pred = np.asarray(logits).argmax(-1)
    labels = np.asarray(labels)
    out = {"accuracy": float((pred == labels).mean())}
    f1s = []
    for i, name in enumerate(LABELS):
        tp = int(((pred == i) & (labels == i)).sum())
        fp = int(((pred == i) & (labels != i)).sum())
        fn = int(((pred != i) & (labels == i)).sum())
        f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        out[f"f1_{name}"] = round(f1, 4)
        # A class absent from the evaluation set would otherwise drag the macro
        # average toward zero for a reason that has nothing to do with the model.
        if (labels == i).sum():
            f1s.append(f1)
    out["macro_f1"] = round(float(np.mean(f1s)), 4) if f1s else 0.0
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="biomedbert-base", help="key in encoders.py")
    ap.add_argument("--train", type=Path, default=DEFAULT_TRAIN)
    ap.add_argument("--train-candidates", type=Path, default=DEFAULT_TRAIN_CANDS)
    ap.add_argument("--test", type=Path, default=DEFAULT_TEST)
    ap.add_argument("--test-candidates", type=Path, default=DEFAULT_TEST_CANDS)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--grad-accum", type=int, default=None)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--patience", type=int, default=2)
    ap.add_argument("--frozen-layers", type=int, default=0)
    ap.add_argument("--val-fraction", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0, help="truncate the training set, for a smoke test")
    ap.add_argument("--save-model", action=argparse.BooleanOptionalAction, default=False)
    args = ap.parse_args()

    spec = encoders.resolve(args.model)
    tokenizer = spec.load_tokenizer()
    batch_size = args.batch_size or spec.batch_size
    grad_accum = args.grad_accum or spec.grad_accum

    train_rows, train_stats = build(args.train, args.train_candidates, tokenizer, args.max_len)
    test_rows, test_stats = build(args.test, args.test_candidates, tokenizer, args.max_len)

    # Split by PMID: pairs from one abstract are far from independent, and
    # letting them straddle the split would leak.
    pmids = sorted({r["pmid"] for r in train_rows})
    random.Random(args.seed).shuffle(pmids)
    n_val = max(1, int(len(pmids) * args.val_fraction))
    val_pmids = set(pmids[:n_val])
    val_rows = [r for r in train_rows if r["pmid"] in val_pmids]
    fit_rows = [r for r in train_rows if r["pmid"] not in val_pmids]
    if args.limit:
        fit_rows = fit_rows[: args.limit]

    torch.manual_seed(args.seed)
    model = AutoModelForSequenceClassification.from_pretrained(
        spec.hf_id,
        num_labels=len(LABELS),
        id2label={i: l for l, i in LABEL2ID.items()},
        label2id=LABEL2ID,
    )
    if args.frozen_layers:
        for i in range(args.frozen_layers):
            needle = spec.frozen_layer_pattern.format(i=i)
            for name, p in model.named_parameters():
                if needle in name:
                    p.requires_grad = False

    run = args.run_name or f"{args.model}_lr{args.lr:g}_e{args.epochs}_fz{args.frozen_layers}"
    out = args.outdir / run
    out.mkdir(parents=True, exist_ok=True)

    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        warmup_steps=0.1,  # a float below 1 is a ratio of total steps (transformers >= 5.17)
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        save_total_limit=1,
        logging_steps=50,
        seed=args.seed,
        bf16=torch.cuda.is_available(),
        report_to=[],
        dataloader_num_workers=2,
    )
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=PairDataset(fit_rows, tokenizer, args.max_len),
        eval_dataset=PairDataset(val_rows, tokenizer, args.max_len),
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.patience)],
    )
    trainer.train()

    val_metrics = trainer.evaluate()
    test_metrics = trainer.evaluate(
        PairDataset(test_rows, tokenizer, args.max_len), metric_key_prefix="test"
    )

    result = {
        "run": run,
        "model_key": args.model,
        "hf_id": spec.hf_id,
        "lr": args.lr,
        "epochs": args.epochs,
        "frozen_layers": args.frozen_layers,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "max_len": args.max_len,
        "seed": args.seed,
        "n_fit": len(fit_rows),
        "n_val": len(val_rows),
        "n_test": len(test_rows),
        "fit_label_counts": {LABELS[i]: n for i, n in Counter(r["label"] for r in fit_rows).items()},
        "test_label_counts": {LABELS[i]: n for i, n in Counter(r["label"] for r in test_rows).items()},
        "build_stats": {"train": train_stats, "test": test_stats},
        "val": {k: v for k, v in val_metrics.items() if k.startswith("eval_")},
        "test": {k: v for k, v in test_metrics.items() if k.startswith("test_")},
    }
    (out / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    if args.save_model:
        trainer.save_model(str(out / "model"))
        tokenizer.save_pretrained(str(out / "model"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
