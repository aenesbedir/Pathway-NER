#!/usr/bin/env python3
"""Create a reproducible grouped, stratified PMID-level split.

The split is random by design, so it starts a new evaluation line rather than
extending a historical benchmark. Exact duplicate texts stay in one split to
prevent train/test leakage. When ``--matches`` is supplied, documents are
stratified by selected-span count so positive/negative and entity-density bands
remain comparable across train, validation, and test.
"""

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SPLIT_NAMES = ("train", "val", "test")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_articles(path: Path) -> dict[str, str]:
    articles: dict[str, str] = {}
    for line in path.open(encoding="utf-8"):
        record = json.loads(line)
        pmid = str(record["pmid"])
        if pmid in articles:
            raise SystemExit(f"duplicate PMID in {path}: {pmid}")
        text = record.get("abstract")
        if not isinstance(text, str) or not text:
            raise SystemExit(f"missing abstract for PMID {pmid} in {path}")
        articles[pmid] = text
    return articles


def load_span_counts(path: Path, article_pmids: set[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for line in path.open(encoding="utf-8"):
        record = json.loads(line)
        pmid = str(record["pmid"])
        if pmid not in article_pmids:
            raise SystemExit(f"PMID {pmid} in {path} is absent from articles")
        counts[pmid] += len(record.get("spans", []))
    return dict(counts)


def span_band(count: int) -> str:
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    if count <= 4:
        return "3-4"
    return "5+"


def split_targets(n: int, train_ratio: float, val_ratio: float) -> dict[str, int]:
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    return {
        "train": n_train,
        "val": n_val,
        "test": n - n_train - n_val,
    }


def assign_groups(
    articles: dict[str, str],
    span_counts: dict[str, int] | None,
    targets: dict[str, int],
    seed: int,
    group_identical_text: bool,
) -> tuple[dict[str, list[str]], dict[str, str], int]:
    groups: dict[str, list[str]] = defaultdict(list)
    for pmid, text in articles.items():
        key = text if group_identical_text else pmid
        groups[key].append(pmid)

    stratum_of = {
        pmid: span_band(span_counts.get(pmid, 0)) if span_counts is not None else "all"
        for pmid in articles
    }
    stratum_totals = Counter(stratum_of.values())
    ratios = {
        name: targets[name] / len(articles)
        for name in SPLIT_NAMES
    }

    rng = random.Random(seed)
    work = []
    for key, pmids in groups.items():
        pmids.sort()
        group_strata = Counter(stratum_of[pmid] for pmid in pmids)
        work.append((-len(pmids), rng.random(), key, pmids, group_strata))
    work.sort()

    assignment = {name: [] for name in SPLIT_NAMES}
    remaining = targets.copy()
    assigned_strata = {name: Counter() for name in SPLIT_NAMES}

    for neg_size, _, _, pmids, group_strata in work:
        size = -neg_size
        candidates = [name for name in SPLIT_NAMES if remaining[name] >= size]
        if not candidates:
            raise SystemExit(
                f"cannot place a duplicate-text group of {size} records into "
                f"remaining split capacities {remaining}"
            )

        def score(name: str) -> tuple[float, float, int]:
            stratum_deficit = sum(
                (
                    ratios[name] * stratum_totals[stratum]
                    - assigned_strata[name][stratum]
                )
                / max(ratios[name] * stratum_totals[stratum], 1.0)
                * count
                for stratum, count in group_strata.items()
            )
            remaining_fraction = remaining[name] / max(targets[name], 1)
            return stratum_deficit, remaining_fraction, -SPLIT_NAMES.index(name)

        destination = max(candidates, key=score)
        assignment[destination].extend(pmids)
        remaining[destination] -= size
        assigned_strata[destination].update(group_strata)

    if any(remaining.values()):
        raise SystemExit(f"split assignment did not fill targets: {remaining}")
    for pmids in assignment.values():
        pmids.sort()

    duplicate_groups = sum(len(pmids) > 1 for pmids in groups.values())
    return assignment, stratum_of, duplicate_groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", required=True,
                        help="JSONL containing one article per PMID")
    parser.add_argument("--matches",
                        help="Optional selected-label matches JSONL. When supplied, "
                             "stratify by span-count band.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--group-identical-text", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Keep exact duplicate abstracts in one split (default: on)")
    args = parser.parse_args()

    if not 0 < args.train_ratio < 1:
        raise SystemExit("--train-ratio must be between 0 and 1")
    if not 0 <= args.val_ratio < 1:
        raise SystemExit("--val-ratio must be between 0 and 1")
    if args.train_ratio + args.val_ratio >= 1:
        raise SystemExit("train and validation ratios must sum to less than 1")

    articles_path = Path(args.articles)
    matches_path = Path(args.matches) if args.matches else None
    articles = load_articles(articles_path)
    span_counts = (
        load_span_counts(matches_path, set(articles))
        if matches_path is not None else None
    )
    targets = split_targets(len(articles), args.train_ratio, args.val_ratio)
    assignment, stratum_of, duplicate_groups = assign_groups(
        articles, span_counts, targets, args.seed, args.group_identical_text
    )

    strata = {
        name: dict(sorted(Counter(stratum_of[pmid] for pmid in pmids).items()))
        for name, pmids in assignment.items()
    }
    payload = {
        "source": f"random PMID split of all articles in {articles_path}",
        "articles_sha256": file_sha256(articles_path),
        "matches": str(matches_path) if matches_path is not None else None,
        "matches_sha256": file_sha256(matches_path) if matches_path is not None else None,
        "seed": args.seed,
        "train_ratio": args.train_ratio,
        "val_ratio": args.val_ratio,
        "test_ratio": 1 - args.train_ratio - args.val_ratio,
        "n_pmids": len(articles),
        "group_identical_text": args.group_identical_text,
        "duplicate_text_groups": duplicate_groups,
        "stratification": "selected_span_count: 0, 1, 2, 3-4, 5+"
                          if span_counts is not None else None,
        "strata": strata,
        **assignment,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for name in SPLIT_NAMES:
        print(f"{name}: {len(assignment[name])}  strata={strata[name]}")
    print(f"duplicate text groups kept together: {duplicate_groups}")
    print(f"total: {len(articles)}")
    print(f"wrote: {output_path}")


if __name__ == "__main__":
    main()
