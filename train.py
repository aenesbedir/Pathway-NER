#!/usr/bin/env python3
"""
train.py — Step 6

Fine-tunes BiomedBERT for metabolic pathway NER using HuggingFace Trainer.

Strategy:
  - Fine-tune all layers (no freezing) — same domain as pre-training
  - Weighted cross-entropy loss to handle 98.6% O token imbalance
  - Early stopping on entity-level val F1 (patience=5)
  - Best checkpoint saved by val F1

Input:  data/processed/train.jsonl
        data/processed/val.jsonl
        data/processed/test.jsonl
Output: models/pathway-ner/   (best checkpoint)

Run with:
    venv310/bin/python3 train.py
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from datasets import Dataset
from seqeval.metrics import f1_score, precision_score, recall_score
from transformers import (
    AutoTokenizer,
    BertForTokenClassification,
    DataCollatorForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL_NAME = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"

LABEL2ID = {"O": 0, "B-Pathway": 1, "I-Pathway": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}
NUM_LABELS = len(LABEL2ID)

# Class weights: down-weight O (0), up-weight B and I
CLASS_WEIGHTS = [0.1, 5.0, 3.0]  # O, B-Pathway, I-Pathway

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/processed",
                        help="Directory containing train/val/test.jsonl")
    parser.add_argument("--output-dir", default="models/pathway-ner-005",
                        help="Output directory for best checkpoint")
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

def load_dataset(path: Path) -> Dataset:
    records = [json.loads(l) for l in path.open(encoding="utf-8")]
    return Dataset.from_list([
        {
            "input_ids": r["input_ids"],
            "attention_mask": r["attention_mask"],
            "labels": r["labels"],
        }
        for r in records
    ])


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

def compute_metrics(eval_pred):
    logits, labels = eval_pred
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
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Data dir   : %s", data_dir)
    log.info("Output dir : %s", output_dir)

    log.info("Loading datasets …")
    train_dataset = load_dataset(data_dir / "train.jsonl")
    val_dataset = load_dataset(data_dir / "val.jsonl")
    test_dataset = load_dataset(data_dir / "test.jsonl")
    log.info("Train: %d  Val: %d  Test: %d", len(train_dataset), len(val_dataset), len(test_dataset))

    log.info("Loading model: %s", MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = BertForTokenClassification.from_pretrained(
        MODEL_NAME,
        num_labels=NUM_LABELS,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    # Freeze bottom 6 BERT layers (embeddings + layers 0-5)
    for name, param in model.named_parameters():
        if "embeddings" in name or any(f"encoder.layer.{i}." in name for i in range(9)):
            param.requires_grad = False
    frozen = sum(1 for p in model.parameters() if not p.requires_grad)
    total = sum(1 for p in model.parameters())
    log.info("Frozen params: %d / %d", frozen, total)

    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer, padding=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=20,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        learning_rate=3e-5,
        weight_decay=0.01,
        warmup_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=20,
        save_total_limit=2,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    trainer = WeightedLossTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=5)],
    )

    log.info("Starting training …")
    trainer.train()

    log.info("Evaluating on test set …")
    test_results = trainer.evaluate(test_dataset)
    log.info("─" * 60)
    log.info("Test F1        : %.4f", test_results.get("eval_f1", 0))
    log.info("Test Precision : %.4f", test_results.get("eval_precision", 0))
    log.info("Test Recall    : %.4f", test_results.get("eval_recall", 0))
    log.info("─" * 60)

    log.info("Saving best model to %s", output_dir)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Save test results
    results_path = output_dir / "test_results.json"
    results_path.write_text(json.dumps(test_results, indent=2), encoding="utf-8")
    log.info("Test results saved to %s", results_path)


if __name__ == "__main__":
    main()
