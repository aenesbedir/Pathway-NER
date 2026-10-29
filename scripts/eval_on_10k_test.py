"""Evaluate saved checkpoints on the pathway-10k test split.

Every model listed in doccano/golden_dataset/gt_100_scores.json is scored with
the same entity-level seqeval metric train.py uses, so the numbers are directly
comparable to the `test_f1` recorded by the pathway-10k sweep.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from seqeval.metrics import f1_score, precision_score, recall_score
from transformers import AutoModelForTokenClassification, AutoTokenizer

ID2LABEL = {0: "O", 1: "B-Pathway", 2: "I-Pathway"}

# checkpoint -> tokenizer-specific pathway-10k dataset directory
MODELS = [
    ("runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7", "biom-electra-large"),
    ("runs-truba-checkpoints/pathway-10k/bioelectra-base/lr3e-05/seed7", "bioelectra-base"),
    ("runs-truba-checkpoints/pathway-10k/biomedbert-base/lr5e-05/seed1", "biomedbert-base"),
    ("runs-truba-checkpoints/pathway-10k/biolinkbert-base/lr5e-05/seed7", "biolinkbert-base"),
    ("runs-truba-checkpoints/pathway-10k/biolinkbert-large/lr3e-05/seed1", "biolinkbert-large"),
    ("models/pathway-ner-gold-wave4-random-all-biomedbert-base", "biomedbert-base"),
    ("models/pathway-ner-gold-wave4-biomedbert-base-min30", "biomedbert-base"),
    ("models/pathway-ner-gold-wave4-biomedbert-base", "biomedbert-base"),
    ("models/pathway-ner-gold-wave4-random-all-bio-modernbert-base/checkpoint-160", "bio-modernbert-base"),
]


def read_split(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh]


def training_pmids(model_dir: Path) -> set[str]:
    """PMIDs a gold-trained checkpoint saw during training/validation.

    The pathway-10k test split is random over the same 10,125 documents, so a
    checkpoint trained on gold-wave4 has partly seen it; the clean subset below
    removes those documents.
    """
    results = model_dir / "test_results.json"
    if not results.exists():
        results = model_dir.parent / "test_results.json"
    if not results.exists():
        return set()
    data_dir = Path(json.loads(results.read_text()).get("data_dir", ""))
    seen: set[str] = set()
    for split in ("train", "val"):
        path = data_dir / f"{split}.jsonl"
        if path.exists():
            seen |= {rec["pmid"] for rec in read_split(path)}
    return seen


def seqeval_scores(true_tags, pred_tags) -> dict:
    return {
        "f1": round(float(f1_score(true_tags, pred_tags)), 4),
        "precision": round(float(precision_score(true_tags, pred_tags)), 4),
        "recall": round(float(recall_score(true_tags, pred_tags)), 4),
    }


def evaluate(model_dir: Path, data_dir: Path, batch_size: int, device: str) -> dict:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForTokenClassification.from_pretrained(model_dir).to(device).eval()

    records = read_split(data_dir / "test.jsonl")
    pad_id = tokenizer.pad_token_id

    seen = training_pmids(model_dir)

    true_tags: list[list[str]] = []
    pred_tags: list[list[str]] = []
    pmids: list[str] = []

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        width = max(len(r["input_ids"]) for r in batch)

        input_ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
        attention = torch.zeros((len(batch), width), dtype=torch.long)
        labels = np.full((len(batch), width), -100, dtype=np.int64)

        for i, rec in enumerate(batch):
            n = len(rec["input_ids"])
            input_ids[i, :n] = torch.tensor(rec["input_ids"], dtype=torch.long)
            attention[i, :n] = torch.tensor(rec["attention_mask"], dtype=torch.long)
            labels[i, :n] = np.array(rec["labels"], dtype=np.int64)

        with torch.no_grad():
            logits = model(
                input_ids=input_ids.to(device),
                attention_mask=attention.to(device),
            ).logits
        preds = logits.argmax(dim=-1).cpu().numpy()

        for rec, pred_seq, label_seq in zip(batch, preds, labels):
            keep = label_seq != -100
            true_tags.append([ID2LABEL[int(x)] for x in label_seq[keep]])
            pred_tags.append([ID2LABEL[int(x)] for x in pred_seq[keep]])
            pmids.append(rec["pmid"])

    out = {"n_records": len(records), **seqeval_scores(true_tags, pred_tags)}

    n_seen = sum(1 for p in pmids if p in seen)
    if n_seen:
        clean = [i for i, p in enumerate(pmids) if p not in seen]
        out["n_records_seen_in_training"] = n_seen
        out["clean_subset"] = {
            "n_records": len(clean),
            **seqeval_scores([true_tags[i] for i in clean], [pred_tags[i] for i in clean]),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--output", default="analysis/eval_10k_test.json")
    args = parser.parse_args()

    results = []
    for model_dir, data_slug in MODELS:
        data_dir = Path("data/processed") / f"pathway-10k-{data_slug}"
        scores = evaluate(Path(model_dir), data_dir, args.batch_size, args.device)
        scores["model"] = model_dir
        scores["data_dir"] = str(data_dir)
        results.append(scores)
        print(f"{model_dir}\tf1={scores['f1']}\tp={scores['precision']}\tr={scores['recall']}", flush=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"split": "pathway-10k test", "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
