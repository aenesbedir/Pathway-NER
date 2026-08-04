#!/usr/bin/env python3
"""Create a reproducible random PMID-level train/validation/test split.

Unlike ``make_splits.py``, this deliberately creates a new evaluation split. It
is intended for isolated experiments, not comparison with results on a frozen
historical split.
"""

import argparse
import json
import random
from pathlib import Path


def load_pmids(path: Path) -> list[str]:
    seen: set[str] = set()
    pmids: list[str] = []
    for line in path.open(encoding="utf-8"):
        pmid = str(json.loads(line)["pmid"])
        if pmid in seen:
            raise SystemExit(f"duplicate PMID in {path}: {pmid}")
        seen.add(pmid)
        pmids.append(pmid)
    return pmids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", required=True,
                        help="JSONL containing one article per PMID")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    args = parser.parse_args()

    if not 0 < args.train_ratio < 1:
        raise SystemExit("--train-ratio must be between 0 and 1")
    if not 0 <= args.val_ratio < 1:
        raise SystemExit("--val-ratio must be between 0 and 1")
    if args.train_ratio + args.val_ratio >= 1:
        raise SystemExit("train and validation ratios must sum to less than 1")

    articles_path = Path(args.articles)
    pmids = sorted(load_pmids(articles_path))
    random.Random(args.seed).shuffle(pmids)

    n = len(pmids)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)
    assignment = {
        "train": pmids[:n_train],
        "val": pmids[n_train:n_train + n_val],
        "test": pmids[n_train + n_val:],
    }
    payload = {
        "source": f"random PMID split of all articles in {articles_path}",
        "seed": args.seed,
        "train_ratio": args.train_ratio,
        "val_ratio": args.val_ratio,
        "test_ratio": 1 - args.train_ratio - args.val_ratio,
        "n_pmids": n,
        **assignment,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for name in ("train", "val", "test"):
        print(f"{name}: {len(assignment[name])}")
    print(f"total: {n}")
    print(f"wrote: {output_path}")


if __name__ == "__main__":
    main()
