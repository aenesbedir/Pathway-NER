#!/usr/bin/env python3
"""
gt100_to_candidates.py

Select the gt_100 pairs that were labelled under schema v3, from the candidate
pool, so the panel can be re-labelled through the ordinary teacher path.

What this script does, and what it must not do
----------------------------------------------
Two files describe the same pairs:

`data/processed/gt_100/gt_100_disease_pathway_*_relation_fable.jsonl`
    181 v3 relation records. Each row carries the ONE pathway mention and the ONE
    disease mention the label was read from - not every occurrence of either
    entity in the abstract.

`data/processed/relation/gt_100/candidates.jsonl`
    1,093 candidates built by `build_candidates.py` straight from the corpus,
    each carrying EVERY occurrence of both entities, with `stratum` and
    `shared_sentences` computed from the complete lists.

The pair set has to come from the first file, so that the v3 and v4 labellings
describe the same pairs and remain comparable. The mentions have to come from
the second, and an earlier version of this script got that wrong: it rebuilt the
candidates out of the relation rows, so a pair whose disease occurs twenty times
reached the teacher with one occurrence marked and nineteen unmarked. In `single`
mode the guide tells the model that unmarked entities are not its concern, so
those runs asked about an entity the abstract mostly did not appear to contain,
and 41 of 180 pairs were additionally recorded as `doc_level` when the two
entities do share a sentence.

`candidate_id` is what makes the join safe: it is a digest of
(namespace, pmid, pathway_key, disease_key) over a namespace frozen at
`pathway_disease_v3`, so the same pair carries the same id in both files even
though the label set has since changed.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from schema import Candidate, RecordError, normalize_surface, read_jsonl, write_jsonl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_LABELS = REPO / (
    "data/processed/gt_100/"
    "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable.jsonl"
)
DEFAULT_POOL = REPO / "data/processed/relation/gt_100/candidates.jsonl"
DEFAULT_OUT = REPO / "data/processed/gt_100/candidates_v4.jsonl"


def wanted_ids(labels: Path) -> dict[str, tuple[str, str, str]]:
    """candidate_id -> identity, for every pair named by the v3 relation file.

    The id in the file is trusted only after it is re-derived from the identity,
    so a stale or hand-edited id cannot silently pull in a different pair.
    """
    from schema import candidate_id

    out: dict[str, tuple[str, str, str]] = {}
    for row in read_jsonl(labels):
        identity = (
            str(row["pmid"]),
            normalize_surface(row["pathway"]["text"]),
            normalize_surface(row["disease"]["text"]),
        )
        out[candidate_id(*identity)] = identity
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS,
                    help="v3 relation file naming the pairs to keep")
    ap.add_argument("--pool", type=Path, default=DEFAULT_POOL,
                    help="candidate pool carrying the complete mention lists")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    want = wanted_ids(args.labels)
    pool = {c["candidate_id"]: c for c in read_jsonl(args.pool)}

    kept: list[Candidate] = []
    missing: list[tuple[str, str, str]] = []
    rejected: collections.Counter = collections.Counter()

    for cid, identity in want.items():
        row = pool.get(cid)
        if row is None:
            missing.append(identity)
            continue
        cand = Candidate.from_json(row)
        try:
            cand.check()
        except RecordError as exc:
            rejected[f"schema_invalid:{str(exc)[:40]}"] += 1
            continue
        kept.append(cand)

    kept.sort(key=lambda c: (c.pmid, c.pathway_key, c.disease_key))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = write_jsonl(args.out, kept)

    mentions = [len(c.pathway_mentions) + len(c.disease_mentions) for c in kept]
    summary = {
        "labels": str(args.labels),
        "pool": str(args.pool),
        "n_pairs_named": len(want),
        "n_candidates": n,
        "n_pmids": len({c.pmid for c in kept}),
        "n_missing_from_pool": len(missing),
        "missing": [list(m) for m in missing[:10]],
        "strata": dict(collections.Counter(c.stratum for c in kept).most_common()),
        "mentions_per_candidate": {
            "min": min(mentions, default=0),
            "median": sorted(mentions)[len(mentions) // 2] if mentions else 0,
            "max": max(mentions, default=0),
        },
        "rejected": dict(rejected.most_common()),
        "out": str(args.out),
    }
    print(json.dumps(summary, indent=2), file=sys.stderr)
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
