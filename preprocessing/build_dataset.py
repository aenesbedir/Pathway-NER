#!/usr/bin/env python3
"""
build_dataset.py — Step 5

Filters, splits, and writes the final NER dataset from bio_tags.jsonl.

Split strategy: stratified by pathway — all records belonging to the same
pathway go to the same split. This prevents the model from seeing the same
pathway name in both train and test (data leakage).

Ratios: 80% train / 10% val / 10% test  (applied at pathway level)

Input:  data/processed/bio_tags.jsonl
Output: data/processed/train.jsonl
        data/processed/val.jsonl
        data/processed/test.jsonl

Run with:
    python3 preprocessing/build_dataset.py
"""

import json
import logging
import random
from collections import defaultdict
from pathlib import Path

BIO_TAGS = Path("data/processed/bio_tags.jsonl")
OUT_DIR = Path("data/processed")

TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
# TEST_RATIO = remaining 10%

SEED = 42

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    # Load and filter
    records = [json.loads(l) for l in BIO_TAGS.open(encoding="utf-8")]
    log.info("Loaded: %d records", len(records))

    records = [r for r in records if any(l in (1, 2) for l in r["labels"])]
    log.info("After filtering (no positive labels removed): %d records", len(records))

    # Group records by primary pathway (first pathway_id)
    pathway_to_records: dict[str, list] = defaultdict(list)
    for r in records:
        primary = r["pathway_ids"][0]
        pathway_to_records[primary].append(r)

    pathways = sorted(pathway_to_records.keys())
    random.seed(SEED)
    random.shuffle(pathways)

    n = len(pathways)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)

    train_pathways = set(pathways[:n_train])
    val_pathways = set(pathways[n_train: n_train + n_val])
    test_pathways = set(pathways[n_train + n_val:])

    train, val, test = [], [], []
    for pathway, recs in pathway_to_records.items():
        if pathway in train_pathways:
            train.extend(recs)
        elif pathway in val_pathways:
            val.extend(recs)
        else:
            test.extend(recs)

    # Write
    splits = {"train": train, "val": val, "test": test}
    for name, split_records in splits.items():
        path = OUT_DIR / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in split_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    log.info("─" * 60)
    log.info("Split          Pathways   Records   Pos labels")
    for name, split_records in splits.items():
        n_pathways = len({r["pathway_ids"][0] for r in split_records})
        pos = sum(l in (1, 2) for r in split_records for l in r["labels"])
        log.info("  %-10s   %-9d  %-9d  %d", name, n_pathways, len(split_records), pos)
    log.info("─" * 60)
    log.info("Output: %s/{train,val,test}.jsonl", OUT_DIR)


if __name__ == "__main__":
    main()
