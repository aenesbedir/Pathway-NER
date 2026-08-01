#!/usr/bin/env python3
"""
build_dataset.py — Step 5

Filters, splits, and writes the final NER dataset from bio_tags.jsonl.

Split strategy: by PMID — all records (abstract + full-text windows) from the
same article go to the same split. This prevents data leakage where the model
would train on one window and evaluate on another from the same article.

`--splits` (frozen assignment, required for any cross-model comparison)
--------------------------------------------------------------------
With `--splits`, each PMID is looked up in `splits.json` and nothing is shuffled.
This is the only mode in which two encoders can be compared.

Without it, the legacy path applies: drop records that carry no positive label,
then shuffle the surviving PMIDs at `SEED`. That order is the problem. The
positive-label filter runs *after* tokenization, so the number of surviving
documents depends on the tokenizer — 1083 becomes 1076 under BiomedBERT's 512
tokens, and stays 1083 under a ModernBERT's 8192. Shuffling a 1076-element list
and a 1083-element list with the same seed gives unrelated permutations, so every
encoder would be scored on a different test set with no sign of it in the logs.

Because a tokenizer decides which documents survive, the two directions of
mismatch against a frozen split are both normal and are logged rather than
raised:
  - `n_unassigned` — in the data, in no split (a long-context model resurrects
    the 7 documents that 512-token truncation had killed);
  - `n_missing`    — in the split, not in the data (another vocabulary may
    truncate a *different* document to death).
Only a gross mismatch (>5% of a split) means the wrong file and aborts.

Default (gold data):
  venv310/bin/python3 preprocessing/build_dataset.py \\
      --input  data/processed/gold-biomedbert-base/bio_tags.jsonl \\
      --outdir data/processed/gold-biomedbert-base \\
      --splits data/processed/gold/splits.json
"""

import argparse
import json
import logging
import random
import shutil
from collections import defaultdict
from pathlib import Path

TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
SEED = 42
MAX_MISSING_FRACTION = 0.05

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
    parser.add_argument(
        "--splits",
        default=None,
        help="Frozen PMID assignment from make_splits.py. Required for any "
             "cross-model comparison; without it the legacy shuffle applies and "
             "the split becomes tokenizer-dependent",
    )
    args = parser.parse_args()

    bio_tags_path = Path(args.input)
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Input  : %s", bio_tags_path)
    log.info("Outdir : %s", out_dir)
    log.info("Splits : %s", args.splits or "(none — legacy shuffle, not comparable)")

    records = [json.loads(l) for l in bio_tags_path.open(encoding="utf-8")]
    log.info("Loaded: %d records", len(records))

    records = [r for r in records if any(l in (1, 2) for l in r["labels"])]
    log.info("After filtering (no positive labels removed): %d records", len(records))

    # Group records by PMID — all records (abstract + full-text windows) from
    # the same article must land in the same split to prevent leakage.
    pmid_to_records: dict[str, list] = defaultdict(list)
    for r in records:
        pmid_to_records[r["pmid"]].append(r)

    if args.splits:
        assignment = json.loads(Path(args.splits).read_text(encoding="utf-8"))
        of_split = {pmid: name
                    for name in ("train", "val", "test")
                    for pmid in assignment[name]}
        unassigned = sorted(set(pmid_to_records) - set(of_split))
    else:
        pmids = sorted(pmid_to_records.keys())
        random.seed(SEED)
        random.shuffle(pmids)

        n = len(pmids)
        n_train = int(n * TRAIN_RATIO)
        n_val = int(n * VAL_RATIO)

        of_split = {p: "train" for p in pmids[:n_train]}
        of_split.update({p: "val" for p in pmids[n_train: n_train + n_val]})
        of_split.update({p: "test" for p in pmids[n_train + n_val:]})
        unassigned = []
        assignment = None

    splits: dict[str, list] = {"train": [], "val": [], "test": []}
    for pmid, recs in pmid_to_records.items():
        name = of_split.get(pmid)
        if name is not None:
            splits[name].extend(recs)

    # Write
    for name, split_records in splits.items():
        path = out_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in split_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary. n_kept is the effective evaluation size — a tokenizer that
    # truncates a document to death removes it from whichever split it was
    # frozen into, so this is not always equal to n_assigned.
    log.info("─" * 60)
    log.info("Split       assigned    kept   missing   Records   Pos labels")
    for name, split_records in splits.items():
        kept = {r["pmid"] for r in split_records}
        n_assigned = len(assignment[name]) if assignment else len(kept)
        n_missing = n_assigned - len(kept)
        pos = sum(l in (1, 2) for r in split_records for l in r["labels"])
        log.info("  %-8s  %6d  %6d  %8d  %8d  %d",
                 name, n_assigned, len(kept), n_missing, len(split_records), pos)
        if assignment and n_assigned and n_missing / n_assigned > MAX_MISSING_FRACTION:
            raise SystemExit(
                f"{n_missing}/{n_assigned} PMIDs of the '{name}' split are absent "
                f"from {bio_tags_path} (>{MAX_MISSING_FRACTION:.0%}) — that is a "
                f"mismatched split file, not tokenizer variation"
            )
    log.info("  unassigned (in data, in no split): %d%s",
             len(unassigned), f"  {unassigned}" if unassigned else "")
    log.info("─" * 60)

    # The dataset is only interpretable next to the tokenizer that produced it.
    meta_src = bio_tags_path.parent / "meta.json"
    if meta_src.exists() and meta_src.parent.resolve() != out_dir.resolve():
        shutil.copy2(meta_src, out_dir / "meta.json")

    log.info("Output: %s/{train,val,test}.jsonl", out_dir)


if __name__ == "__main__":
    main()
