#!/usr/bin/env python3
"""
gt100_to_candidates.py

Turn the gt_100 relation file into schema-v4 candidates, so the panel can be
re-labelled through the ordinary teacher path.

Why a converter and not a rebuild
---------------------------------
`data/processed/gt_100/gt_100_disease_pathway_*_relation_fable.jsonl` was written
under a different schema - `pathway_disease_v3:up|down|altered|therapeutic_target|
no_association_stated` - with one row per (disease, pathway) pair and its own
offsets. Rebuilding the panel with `build_candidates.py` would re-run pair
selection and could yield a different pair set, which would make the two
labellings incomparable. This script preserves the pair set exactly and changes
only the record shape.

Nothing is carried over from the old labels. `label`, `certainty` and `evidence`
are dropped on purpose: the point of the re-run is a fresh reading, and a
candidate that carried its previous answer would not be one.

Abstracts
---------
The source file stores offsets but no text. Abstracts are read from
`data/processed/pathway-10k/articles.jsonl` and every offset is re-validated
against the text it is supposed to name; a mention whose surface does not match
is rejected rather than silently shifted.

Sentence segmentation matches `build_candidates.py`: spaCy's rule-based
`sentencizer` over the exact stored abstract, which decides `stratum` and
`shared_sentences`.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import spacy

from schema import (
    Candidate,
    Mention,
    RecordError,
    candidate_id,
    normalize_surface,
    write_jsonl,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO / (
    "data/processed/gt_100/"
    "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable.jsonl"
)
DEFAULT_ARTICLES = REPO / "data/processed/pathway-10k/articles.jsonl"
DEFAULT_OUT = REPO / "data/processed/gt_100/candidates_v4.jsonl"


def read_articles(path: Path) -> dict[str, str]:
    """pmid -> abstract.

    Some records carry a raw newline inside the abstract string, so a record is
    not always a line. Scanning line by line and joining until the buffer parses
    loses everything after the first record it cannot close, so the whole file is
    decoded as a stream of concatenated JSON values instead.
    """
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    out: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        row, i = decoder.raw_decode(text, i)
        out[str(row["pmid"])] = row["abstract"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--articles", type=Path, default=DEFAULT_ARTICLES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    articles = read_articles(args.articles)
    rows = [json.loads(l) for l in args.src.read_text(encoding="utf-8").splitlines() if l.strip()]

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")

    rejected: collections.Counter = collections.Counter()
    # One candidate per (pmid, pathway_key, disease_key); the source may repeat a
    # pair across rows, and the identity digest would collide on the duplicates.
    grouped: dict[tuple[str, str, str], dict] = {}

    for row in rows:
        pmid = str(row["pmid"])
        abstract = articles.get(pmid)
        if abstract is None:
            rejected["abstract_not_found"] += 1
            continue
        p, d = row["pathway"], row["disease"]
        pm = Mention(p["text"], p["start"], p["end"], "PATHWAY")
        dm = Mention(d["text"], d["start"], d["end"], "DISEASE")
        try:
            pm.check(abstract)
            dm.check(abstract)
        except RecordError as exc:
            rejected[f"offset_mismatch:{str(exc)[:40]}"] += 1
            continue
        key = (pmid, normalize_surface(p["text"]), normalize_surface(d["text"]))
        entry = grouped.setdefault(key, {"abstract": abstract, "pathway": [], "disease": []})
        if pm not in entry["pathway"]:
            entry["pathway"].append(pm)
        if dm not in entry["disease"]:
            entry["disease"].append(dm)

    out: list[Candidate] = []
    for (pmid, pkey, dkey), entry in grouped.items():
        abstract = entry["abstract"]
        sents = [(s.start_char, s.end_char) for s in nlp(abstract).sents]
        shared = [
            (a, b)
            for a, b in sents
            if any(a <= m.start and m.end <= b for m in entry["pathway"])
            and any(a <= m.start and m.end <= b for m in entry["disease"])
        ]
        cand = Candidate(
            candidate_id=candidate_id(pmid, pkey, dkey),
            pmid=pmid,
            abstract=abstract,
            pathway_key=pkey,
            disease_key=dkey,
            pathway_mentions=sorted(entry["pathway"], key=lambda m: m.start),
            disease_mentions=sorted(entry["disease"], key=lambda m: m.start),
            shared_sentences=shared,
            stratum="same_sentence" if shared else "doc_level",
        )
        try:
            cand.check()
        except RecordError as exc:
            rejected[f"schema_invalid:{str(exc)[:40]}"] += 1
            continue
        out.append(cand)

    out.sort(key=lambda c: (c.pmid, c.pathway_key, c.disease_key))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = write_jsonl(args.out, out)

    summary = {
        "source": str(args.src),
        "n_source_rows": len(rows),
        "n_candidates": n,
        "n_pmids": len({c.pmid for c in out}),
        "strata": dict(collections.Counter(c.stratum for c in out).most_common()),
        "rejected": dict(rejected.most_common()),
        "spacy_version": spacy.__version__,
        "out": str(args.out),
    }
    print(json.dumps(summary, indent=2), file=sys.stderr)
    (args.out.with_suffix(".summary.json")).write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
