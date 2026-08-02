#!/usr/bin/env python3
"""
make_splits.py — freeze the train/val/test assignment

Writes `data/processed/gold/splits.json`, the committed contract every model's
dataset is built against.

Why this exists
---------------
`build_dataset.py` used to derive the split itself: it dropped records with no
positive label *after* tokenization, then shuffled the surviving PMID list with
`random.seed(42)`. Under the BiomedBERT tokenizer 1083 documents become 1076,
because 7 abstracts have all their spans past the 512-token cut.

A different tokenizer loses a different number of documents — a ModernBERT at
8192 tokens loses none — and `random.shuffle` over a 1076-element list and over a
1083-element list produce unrelated permutations, not similar ones. Every encoder
would then be scored on a different test set while every log line still read
"Test: 109". Freezing the assignment once removes the coupling entirely.

Snapshot, not re-derivation
---------------------------
The split is copied out of the existing `{train,val,test}.jsonl` rather than
recomputed from `matches.jsonl`. Re-deriving over 1083 PMIDs would produce a
different (equally valid) assignment and silently invalidate every number from
gold-001 to gold-008. The cost of snapshotting is that the 7 truncated documents
stay out of the dataset for every model, so a long-context encoder cannot show
its advantage on them — 19 of 2817 spans, worth reporting separately rather than
worth invalidating eight runs over.

Corpus extension
----------------
When reviewed data grows, ``--base-splits`` preserves the historical train/val/test
and excluded PMID lists, then appends every previously unseen PMID in the new
``matches.jsonl`` to train. Validation and test therefore remain byte-for-byte
comparable while supervision grows.

Run from repo root:
    venv310/bin/python3 preprocessing/make_splits.py

Extend a frozen split with new training supervision:
    venv310/bin/python3 preprocessing/make_splits.py \
        --base-splits data/processed/gold/splits.json \
        --matches data/processed/gold-wave4/matches.jsonl \
        --output data/processed/gold-wave4/splits.json
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SPLITS = ("train", "val", "test")


def pmids_of(path: Path) -> list[str]:
    """Ordered, de-duplicated PMIDs of a bio-tags-shaped JSONL file."""
    seen: dict[str, None] = {}
    for line in path.open(encoding="utf-8"):
        seen.setdefault(str(json.loads(line)["pmid"]), None)
    return list(seen)


def pmids_from_matches(path: Path) -> list[str]:
    """Ordered, de-duplicated PMIDs from a matches JSONL file."""
    seen: dict[str, None] = {}
    for line in path.open(encoding="utf-8"):
        seen.setdefault(str(json.loads(line)["pmid"]), None)
    return list(seen)


def assigned_pmids(assignment: dict[str, list[str]]) -> set[str]:
    """Validate split disjointness and return the assigned PMID set."""
    assigned = {p for name in SPLITS for p in assignment[name]}
    total = sum(len(assignment[name]) for name in SPLITS)
    if total != len(assigned):
        raise SystemExit(
            "a PMID appears in more than one split "
            f"({total} entries, {len(assigned)} unique) — refusing to write"
        )
    return assigned


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir", default="data/processed/gold",
                    help="Directory holding the {train,val,test}.jsonl to snapshot")
    ap.add_argument("--matches", default="data/processed/gold/matches.jsonl",
                    help="Gold spans used to find excluded or newly added PMIDs")
    ap.add_argument("--output", default="data/processed/gold/splits.json")
    ap.add_argument(
        "--base-splits",
        default=None,
        help="Preserve this frozen split and append previously unseen match PMIDs "
             "to train instead of snapshotting --from-dir",
    )
    args = ap.parse_args()

    src = Path(args.from_dir)
    out = Path(args.output)
    matches_path = Path(args.matches)
    all_pmids_ordered = pmids_from_matches(matches_path)
    all_pmids = set(all_pmids_ordered)

    if args.base_splits:
        base_path = Path(args.base_splits)
        base = json.loads(base_path.read_text(encoding="utf-8"))
        assignment = {
            name: [str(pmid) for pmid in base[name]] for name in SPLITS
        }
        base_assigned = assigned_pmids(assignment)
        excluded = [str(pmid) for pmid in base.get("excluded_pmids", [])]
        if len(excluded) != len(set(excluded)):
            raise SystemExit(f"duplicate excluded PMIDs in {base_path}")
        overlap = sorted(base_assigned & set(excluded))
        if overlap:
            raise SystemExit(
                f"{len(overlap)} PMIDs are both assigned and excluded in "
                f"{base_path}: {overlap}"
            )
        known = base_assigned | set(excluded)
        missing = sorted(known - all_pmids)
        if missing:
            raise SystemExit(
                f"{len(missing)} PMIDs from {base_path} are absent from "
                f"{matches_path}: {missing}"
            )
        added = [pmid for pmid in all_pmids_ordered if pmid not in known]
        assignment["train"].extend(added)
        assigned = assigned_pmids(assignment)
        payload = {
            "source": (
                f"extension of {base_path}; all previously unseen positive PMIDs "
                "assigned to train"
            ),
            "base_splits": str(base_path),
            "n_pmids": len(assigned),
            "n_pmids_with_spans": len(all_pmids),
            "n_added_to_train": len(added),
            "excluded_pmids": excluded,
            "excluded_reason": base.get(
                "excluded_reason", "preserved from base split"
            ),
            **assignment,
        }
    else:
        assignment = {name: pmids_of(src / f"{name}.jsonl") for name in SPLITS}
        assigned = assigned_pmids(assignment)
        excluded = sorted(all_pmids - assigned)
        added = []
        payload = {
            "source": (
                f"snapshot of {src}/{{train,val,test}}.jsonl "
                "(the gold-001…008 split)"
            ),
            "n_pmids": len(assigned),
            "n_pmids_with_spans": len(all_pmids),
            "excluded_pmids": excluded,
            "excluded_reason": (
                "no B/I label survived 512-token truncation under the BiomedBERT "
                "tokenizer, so build_dataset.py dropped the record before the split "
                "was drawn"
            ),
            **assignment,
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    log.info("─" * 60)
    for name in SPLITS:
        log.info("  %-6s %4d PMIDs", name, len(assignment[name]))
    log.info("  %-6s %4d PMIDs", "total", len(assigned))
    if args.base_splits:
        log.info("  added to train: %d PMIDs", len(added))
    log.info("  excluded (in matches.jsonl, in no split): %d", len(excluded))
    for pmid in excluded:
        log.info("    %s", pmid)
    log.info("─" * 60)
    log.info("Wrote %s", out)


if __name__ == "__main__":
    main()
