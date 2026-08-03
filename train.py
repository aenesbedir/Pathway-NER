#!/usr/bin/env python3
"""
train.py — Step 6

Fine-tunes a biomedical encoder for metabolic pathway NER using HuggingFace
Trainer. Which encoder is `--model` (see `encoders.py`).

Strategy:
  - Fine-tune all layers (no freezing) — same domain as pre-training
  - Weighted cross-entropy loss to handle the ~98% O token imbalance
  - Early stopping on entity-level val F1
  - Best checkpoint saved by val F1

Input:  <data-dir>/{train,val,test}.jsonl  + meta.json
Output: <output-dir>/   best checkpoint, test_results.json, test_predictions.jsonl

The `input_ids` in <data-dir> only mean something under the tokenizer that wrote
them, and the candidate vocabularies overlap in range (28895 / 30522 / 50368), so
a mismatched pairing raises nothing — it silently trains a worse model and the
bad F1 reads as a verdict on the encoder. `meta.json` is checked against
`--model` before anything loads.

Run with:
    venv310/bin/python3 train.py --model biomedbert-base \\
        --data-dir data/processed/gold-biomedbert-base \\
        --output-dir models/pathway-ner-gold-009
"""

import argparse
import json
import logging
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import transformers
from datasets import Dataset
from seqeval.metrics import f1_score, precision_score, recall_score
from transformers import (
    AutoModelForTokenClassification,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    set_seed,
)

from encoders import resolve, vocab_fingerprint

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LABEL2ID = {"O": 0, "B-Pathway": 1, "I-Pathway": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}
NUM_LABELS = len(LABEL2ID)

# Class weights: down-weight O (0), up-weight B and I. Overridden by the registry
# entry and then by --class-weights.
CLASS_WEIGHTS = [0.1, 5.0, 3.0]  # O, B-Pathway, I-Pathway

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None,
                        help="Encoder registry key or HF id (see "
                             "`python3 encoders.py`)")
    parser.add_argument("--data-dir", default=None,
                        help="Directory containing train/val/test.jsonl "
                             "(default: the registry entry's data dir)")
    parser.add_argument("--output-dir", default="models/pathway-ner-005",
                        help="Output directory for best checkpoint")
    parser.add_argument("--class-weights", nargs=3, type=float,
                        metavar=("O", "B", "I"), default=None,
                        help="CrossEntropy class weights for O / B-Pathway / "
                             "I-Pathway (default: the registry entry's)")
    parser.add_argument("--epochs", type=int, default=20,
                        help="Max training epochs (default: 20)")
    parser.add_argument("--patience", type=int, default=5,
                        help="Early-stopping patience in epochs (default: 5)")
    parser.add_argument("--frozen-layers", type=int, default=9,
                        help="Freeze embeddings + this many bottom encoder layers "
                             "(0 = train everything; default: 9)")
    parser.add_argument("--batch-size", type=int, default=None,
                        help="Per-device train batch size (default: the registry "
                             "entry's, sized for the 8 GB card)")
    parser.add_argument("--grad-accum", type=int, default=None,
                        help="Gradient accumulation steps; batch-size x this is "
                             "the effective batch and should stay 16 across models")
    parser.add_argument("--lr", type=float, default=3e-5,
                        help="Learning rate (default: 3e-5)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Training seed: head init, shuffling, dropout "
                             "(default: 42; does not affect the data split)")
    parser.add_argument("--train-fraction", type=float, default=1.0,
                        help="Train on this fraction of the training PMIDs "
                             "(default 1.0). Used to trace a learning curve: "
                             "whether encoders separate more as supervision grows "
                             "is the question the survey actually rests on, and it "
                             "is measurable now rather than after wave-3")
    parser.add_argument("--subset-seed", type=int, default=42,
                        help="Seed for --train-fraction subsampling. Deliberately "
                             "separate from --seed so every model and every "
                             "training seed sees the *same* subset — otherwise the "
                             "curve measures which documents were drawn")
    parser.add_argument("--splits", default="data/processed/gold/splits.json",
                        help="Frozen split, used to draw --train-fraction subsets "
                             "from a model-independent PMID list")
    parser.add_argument("--save-model", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Keep the fine-tuned weights. --no-save-model keeps "
                             "only test_results.json and test_predictions.jsonl, "
                             "which is all a sweep needs — a checkpoint is ~0.5-1.6 "
                             "GB and a full model x lr x seed matrix would not fit "
                             "on disk")
    return parser.parse_args()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def read_records(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8")]


def to_dataset(records: list[dict]) -> Dataset:
    """Keep only the model's input columns; `pmid` is carried separately so
    predictions can be written back per document."""
    return Dataset.from_list([
        {
            "input_ids": r["input_ids"],
            "attention_mask": r["attention_mask"],
            "labels": r["labels"],
        }
        for r in records
    ])


def subsample_train(records: list[dict], fraction: float, splits_path: Path,
                    subset_seed: int) -> list[dict]:
    """Keep `fraction` of the training PMIDs, identically for every model.

    The subset is drawn from `splits.json` — the model-independent PMID list —
    rather than from the records, because a tokenizer that truncates a document to
    death removes it from that model's records and would otherwise shift the
    subset. Nested by construction: a 25% subset is contained in the 50% one, so
    successive points on a learning curve add documents instead of resampling them.
    """
    if fraction >= 1.0:
        return records

    train_pmids = json.loads(splits_path.read_text(encoding="utf-8"))["train"]
    ordered = sorted(str(p) for p in train_pmids)
    random.Random(subset_seed).shuffle(ordered)
    keep = set(ordered[:max(1, round(len(ordered) * fraction))])
    return [r for r in records if str(r["pmid"]) in keep]


def check_data_matches_model(data_dir: Path, spec, tokenizer) -> dict:
    """Refuse to train on `input_ids` written by a different vocabulary.

    The invariant is the vocabulary, not the checkpoint id: BioLinkBERT (base and
    large), BiomedBERT-large-abstract and BioELECTRA ship byte-identical
    28895-token PubMedBERT vocabularies, so their datasets are genuinely
    interchangeable. BiomedBERT-base-abstract-fulltext's own 30522-token
    vocabulary is a different one of a similar size — the pairing that produces
    in-range nonsense instead of an exception.
    """
    meta_path = data_dir / "meta.json"
    if not meta_path.exists():
        raise SystemExit(
            f"{meta_path} is missing — regenerate the dataset with "
            f"preprocessing/tag_bio.py so the tokenizer is recorded"
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    theirs = meta.get("vocab_fingerprint")
    if theirs is None:                       # meta.json predates the fingerprint
        if meta.get("tokenizer_id") != spec.tokenizer_id:
            raise SystemExit(
                f"tokenizer mismatch: {data_dir} was built with "
                f"{meta.get('tokenizer_id')!r}, --model tokenizes with "
                f"{spec.tokenizer_id!r}. Regenerate the dataset to get a "
                f"vocabulary fingerprint."
            )
        return meta

    ours = vocab_fingerprint(tokenizer)
    if theirs != ours:
        raise SystemExit(
            f"vocabulary mismatch: {data_dir} was tokenized by "
            f"{meta.get('tokenizer_id')!r} (vocab {theirs}), but --model "
            f"{spec.hf_id!r} uses {spec.tokenizer_id!r} (vocab {ours}). The id "
            f"ranges overlap, so this would train silently on nonsense."
        )
    return meta


# ---------------------------------------------------------------------------
# Weighted loss trainer
# ---------------------------------------------------------------------------

class WeightedLossTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits

        weights = torch.tensor(CLASS_WEIGHTS, dtype=torch.float, device=logits.device)
        loss_fn = nn.CrossEntropyLoss(weight=weights, ignore_index=-100)
        loss = loss_fn(logits.view(-1, NUM_LABELS), labels.view(-1))

        return (loss, outputs) if return_outputs else loss


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def to_tag_sequences(logits, labels):
    """(true_tags, pred_tags) per record, with -100 positions dropped."""
    predictions = np.argmax(logits, axis=-1)

    true_labels, pred_labels = [], []
    for pred_seq, label_seq in zip(predictions, labels):
        true_seq, pred_seq_out = [], []
        for p, l in zip(pred_seq, label_seq):
            if l == -100:
                continue
            true_seq.append(ID2LABEL[l])
            pred_seq_out.append(ID2LABEL[p])
        true_labels.append(true_seq)
        pred_labels.append(pred_seq_out)
    return true_labels, pred_labels


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    true_labels, pred_labels = to_tag_sequences(logits, labels)

    return {
        "f1": f1_score(true_labels, pred_labels),
        "precision": precision_score(true_labels, pred_labels),
        "recall": recall_score(true_labels, pred_labels),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    spec = resolve(args.model)
    data_dir = Path(args.data_dir) if args.data_dir else spec.data_dir()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    global CLASS_WEIGHTS
    CLASS_WEIGHTS = list(args.class_weights or spec.class_weights)

    tokenizer = spec.load_tokenizer()
    meta = check_data_matches_model(data_dir, spec, tokenizer)
    set_seed(args.seed)

    use_bf16, use_fp16 = spec.torch_dtype_flags()
    batch_size = args.batch_size or spec.batch_size
    grad_accum = args.grad_accum or spec.grad_accum

    log.info("Model        : %s", spec.hf_id)
    log.info("Data dir     : %s  (tokenizer %s, ctx %s)",
             data_dir, meta.get("tokenizer_class"), meta.get("max_tokens"))
    log.info("Output dir   : %s", output_dir)
    log.info("Class weights: %s", CLASS_WEIGHTS)
    log.info("Learning rate: %s", args.lr)
    log.info("Seed         : %s", args.seed)
    log.info("Precision    : %s", "bf16" if use_bf16 else "fp16" if use_fp16 else "fp32")
    log.info("Batch        : %d x %d accum = %d effective",
             batch_size, grad_accum, batch_size * grad_accum)

    log.info("Loading datasets …")
    train_records = read_records(data_dir / "train.jsonl")
    n_full = len({r["pmid"] for r in train_records})
    train_records = subsample_train(train_records, args.train_fraction,
                                    Path(args.splits), args.subset_seed)
    val_records = read_records(data_dir / "val.jsonl")
    test_records = read_records(data_dir / "test.jsonl")
    train_dataset = to_dataset(train_records)
    val_dataset = to_dataset(val_records)
    test_dataset = to_dataset(test_records)
    n_train_pmids = len({r["pmid"] for r in train_records})
    log.info("Train: %d  Val: %d  Test: %d", len(train_dataset), len(val_dataset), len(test_dataset))
    if args.train_fraction < 1.0:
        log.info("Train fraction: %.2f  (%d of %d PMIDs, subset seed %d)",
                 args.train_fraction, n_train_pmids, n_full, args.subset_seed)

    log.info("Loading model: %s", spec.hf_id)
    model = AutoModelForTokenClassification.from_pretrained(
        spec.hf_id,
        num_labels=NUM_LABELS,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )
    log.info("Architecture : %s", type(model).__name__)

    # Freeze embeddings + the bottom `--frozen-layers` encoder layers
    # (0 = train everything, the gold-004+ recipe). The layer-name pattern is
    # per-family — BERT/ELECTRA use `encoder.layer.{i}.`, ModernBERT uses
    # `layers.{i}.` — and a wrong pattern freezes nothing without complaining.
    if args.frozen_layers > 0:
        patterns = [spec.frozen_layer_pattern.format(i=i)
                    for i in range(args.frozen_layers)]
        matched = 0
        for name, param in model.named_parameters():
            if "embeddings" in name or any(p in name for p in patterns):
                param.requires_grad = False
                matched += 1
        if matched == 0:
            raise SystemExit(
                f"--frozen-layers {args.frozen_layers} matched no parameters "
                f"with pattern {spec.frozen_layer_pattern!r} on "
                f"{type(model).__name__} — fix the registry entry"
            )
    frozen = sum(1 for p in model.parameters() if not p.requires_grad)
    total = sum(1 for p in model.parameters())
    log.info("Frozen bottom layers: %d  (params %d / %d)",
             args.frozen_layers, frozen, total)

    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer, padding=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=max(1, batch_size * 2),
        gradient_accumulation_steps=grad_accum,
        learning_rate=args.lr,
        weight_decay=0.01,
        seed=args.seed,
        warmup_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=20,
        save_total_limit=2,
        bf16=use_bf16,
        fp16=use_fp16,
        report_to="none",
    )

    trainer = WeightedLossTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.patience)],
    )

    log.info("Starting training …")
    started = time.time()
    trainer.train()
    runtime_s = time.time() - started

    log.info("Evaluating on test set …")
    prediction = trainer.predict(test_dataset)
    test_results = dict(prediction.metrics)
    log.info("─" * 60)
    log.info("Test F1        : %.4f", test_results.get("test_f1", 0))
    log.info("Test Precision : %.4f", test_results.get("test_precision", 0))
    log.info("Test Recall    : %.4f", test_results.get("test_recall", 0))
    log.info("─" * 60)

    if args.save_model:
        log.info("Saving best model to %s", output_dir)
        trainer.save_model(str(output_dir))
        tokenizer.save_pretrained(str(output_dir))

    # Per-document tag sequences. `Trainer.predict` preserves dataset order, so
    # zipping with the raw records recovers the PMIDs that `to_dataset` drops.
    # scripts/aggregate_runs.py needs these for the paired bootstrap: on a
    # 109-document test set, comparing two independent confidence intervals is
    # far too blunt to resolve the differences that matter.
    true_tags, pred_tags = to_tag_sequences(prediction.predictions,
                                            prediction.label_ids)
    predictions_path = output_dir / "test_predictions.jsonl"
    with predictions_path.open("w", encoding="utf-8") as f:
        for record, true_seq, pred_seq in zip(test_records, true_tags, pred_tags):
            f.write(json.dumps({"pmid": record["pmid"], "chunk": record.get("chunk", 0),
                                "true": true_seq, "pred": pred_seq}) + "\n")

    # Which epoch `load_best_model_at_end` actually kept. Worth recording: a run
    # that peaks at its last epoch was epoch-limited rather than converged, which
    # happened to gold-002 and made its number an underestimate.
    evals = [h for h in trainer.state.log_history if "eval_f1" in h]
    best = max(evals, key=lambda h: h["eval_f1"], default={})

    # Everything a run needs to be interpretable next to another run.
    test_results.update({
        "best_epoch": best.get("epoch"),
        "best_val_f1": best.get("eval_f1"),
        "epochs_run": evals[-1]["epoch"] if evals else None,
        "model_key": args.model or "biomedbert-base",
        "hf_id": spec.hf_id,
        "data_dir": str(data_dir),
        "lr": args.lr,
        "seed": args.seed,
        "class_weights": list(CLASS_WEIGHTS),
        "epochs": args.epochs,
        "patience": args.patience,
        "frozen_layers": args.frozen_layers,
        "precision_mode": "bf16" if use_bf16 else "fp16" if use_fp16 else "fp32",
        # What the run actually executed on. `precision_mode` alone does not
        # identify it — a V100 and a P100 both report fp16, and the same fp16
        # recipe is a different computation on each. These are read from the
        # process rather than passed in, so a run cannot mislabel itself the way
        # a `--site truba` flag could when someone forgets to pass it.
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "n_train": len(train_dataset),
        "n_train_pmids": n_train_pmids,
        "train_fraction": args.train_fraction,
        "subset_seed": args.subset_seed,
        "n_val": len(val_dataset),
        "n_test_effective": len({r["pmid"] for r in test_records}),
        "runtime_s": round(runtime_s, 1),
    })
    results_path = output_dir / "test_results.json"
    results_path.write_text(json.dumps(test_results, indent=2), encoding="utf-8")
    log.info("Test results saved to %s", results_path)
    log.info("Predictions saved to %s", predictions_path)

    # `load_best_model_at_end` needs the epoch checkpoints during training; once
    # the best weights are in memory and the results are written, they are dead
    # weight on disk.
    for checkpoint in output_dir.glob("checkpoint-*"):
        shutil.rmtree(checkpoint, ignore_errors=True)


if __name__ == "__main__":
    main()
