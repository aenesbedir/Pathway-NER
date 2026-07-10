#!/usr/bin/env python3
"""
build_dataset.py — Step 5

Filters, splits, and writes the final NER dataset from bio_tags.jsonl.

Split strategy: stratified by PMID — all records (abstract + full-text windows)
from the same article go to the same split. This prevents data leakage where
the model would train on one window and evaluate on another from the same article.

Ratios: 80% train / 10% val / 10% test  (applied at pathway level)

Phase 1 (default):
  python3 preprocessing/build_dataset.py

Phase 2:
  python3 preprocessing/build_dataset.py \\
      --input  data/processed/bio_tags_v2.jsonl \\
      --outdir data/processed/phase2

Run with:
    python3 preprocessing/build_dataset.py
"""

import argparse
import json
import logging
import random
from collections import defaultdict
from pathlib import Path

TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
SEED = 42

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/processed/bio_tags.jsonl",
        help="BIO tags JSONL to split (default: Phase 1 bio_tags.jsonl)",
    )
    parser.add_argument(
        "--outdir",
        default="data/processed",
        help="Output directory for train/val/test.jsonl (default: data/processed)",
    )
    args = parser.parse_args()

    bio_tags_path = Path(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Input  : %s", bio_tags_path)
    log.info("Outdir : %s", out_dir)

    records = [json.loads(l) for l in bio_tags_path.open(encoding="utf-8")]
    log.info("Loaded: %d records", len(records))

    records = [r for r in records if any(l in (1, 2) for l in r["labels"])]
    log.info("After filtering (no positive labels removed): %d records", len(records))

    # Group records by PMID — all records (abstract + full-text windows) from
    # the same article must land in the same split to prevent leakage.
    pmid_to_records: dict[str, list] = defaultdict(list)
    for r in records:
        pmid_to_records[r["pmid"]].append(r)

    pmids = sorted(pmid_to_records.keys())
    random.seed(SEED)
    random.shuffle(pmids)

    n = len(pmids)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)

    train_pmids = set(pmids[:n_train])
    val_pmids = set(pmids[n_train: n_train + n_val])
    test_pmids = set(pmids[n_train + n_val:])

    train, val, test = [], [], []
    for pmid, recs in pmid_to_records.items():
        if pmid in train_pmids:
            train.extend(recs)
        elif pmid in val_pmids:
            val.extend(recs)
        else:
            test.extend(recs)

    # Write
    splits = {"train": train, "val": val, "test": test}
    for name, split_records in splits.items():
        path = out_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in split_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    log.info("─" * 60)
    log.info("Split          PMIDs      Records   Pos labels")
    for name, split_records in splits.items():
        n_pmids = len({r["pmid"] for r in split_records})
        pos = sum(l in (1, 2) for r in split_records for l in r["labels"])
        log.info("  %-10s   %-9d  %-9d  %d", name, n_pmids, len(split_records), pos)
    log.info("─" * 60)
    log.info("Output: %s/{train,val,test}.jsonl", out_dir)


if __name__ == "__main__":
    main()
