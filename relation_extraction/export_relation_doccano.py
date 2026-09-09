#!/usr/bin/env python3
"""
export_relation_doccano.py

Turn a teacher relation file into a doccano relation-extraction import file.

Format
------
doccano's `JSONL(Relation)` import, for a Sequence Labeling project with
relation labeling enabled - the shape already used by
`/home/enes/annotations/scripts/export_relations_to_doccano.py`:

    {"text": ..., "entities": [{"id", "start_offset", "end_offset", "label"}],
     "relations": [{"id", "from_id", "to_id", "type"}]}

One document per abstract, not per pair
---------------------------------------
An abstract carrying six pairs becomes one document with six relation edges,
rather than six documents repeating the same text. The annotator reads the
abstract once. It also keeps the review unit identical to the annotation unit
in `schema.py`: one label per (pathway, disease) pair per abstract.

Each edge is drawn between the FIRST mention of each entity. Every other mention
is still exported as an entity so the annotator can see where the entity occurs,
but only one edge per pair exists, so there is exactly one answer to give.

Pre-filled or blind
-------------------
By default the model's label becomes the relation type, and the task is review:
confirm or correct. That anchors the annotator, which is fine for correcting a
corpus and wrong for measuring the teacher - an anchored annotator agrees with
the model more often than an independent one would.

`--blind` writes `UNREVIEWED` on every edge instead. Use it when the number
being produced is teacher accuracy. Edges left as `UNREVIEWED` on the way back
are then countable, which a pre-filled export cannot distinguish from agreement.

Joining the export back
-----------------------
doccano relations carry no metadata of their own, so `meta.pairs` records, for
each edge, the `candidate_id` it belongs to along with the model's answer. The
importer joins on that rather than on offsets.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from schema import Candidate, as_quotes, read_jsonl

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RELATIONS = REPO / (
    "data/processed/gt_100/"
    "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable_v4d_single.jsonl"
)
DEFAULT_CANDIDATES = REPO / "data/processed/gt_100/candidates_v4.jsonl"
DEFAULT_OUT = REPO / "data/processed/gt_100/doccano_relations_import.jsonl"

BLIND_TYPE = "UNREVIEWED"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS)
    ap.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--blind", action="store_true",
                    help="write UNREVIEWED instead of the model's label")
    ap.add_argument("--sample", type=int, default=0,
                    help="keep only the first N abstracts, for a trial import")
    args = ap.parse_args()

    cands = {c.candidate_id: c for c in (Candidate.from_json(d) for d in read_jsonl(args.candidates))}
    labelled = {r["candidate_id"]: r for r in read_jsonl(args.relations)}

    by_pmid: dict[str, list[Candidate]] = collections.defaultdict(list)
    for cid in labelled:
        cand = cands.get(cid)
        if cand is not None:
            by_pmid[cand.pmid].append(cand)

    docs = []
    stats: collections.Counter = collections.Counter()
    for pmid in sorted(by_pmid):
        group = sorted(by_pmid[pmid], key=lambda c: (c.pathway_key, c.disease_key))
        abstract = group[0].abstract

        # One entity per distinct span. A span may belong to several pairs, and
        # doccano needs a single id for it either way.
        span_id: dict[tuple[int, int, str], int] = {}
        entities = []
        for cand in group:
            for m, kind in (
                *[(m, "PATHWAY") for m in cand.pathway_mentions],
                *[(m, "DISEASE") for m in cand.disease_mentions],
            ):
                key = (m.start, m.end, kind)
                if key in span_id:
                    continue
                span_id[key] = len(entities)
                entities.append(
                    {
                        "id": span_id[key],
                        "start_offset": m.start,
                        "end_offset": m.end,
                        "label": kind,
                    }
                )

        relations, pairs = [], []
        for cand in group:
            row = labelled[cand.candidate_id]
            p = cand.pathway_mentions[0]
            d = cand.disease_mentions[0]
            from_id = span_id[(p.start, p.end, "PATHWAY")]
            to_id = span_id[(d.start, d.end, "DISEASE")]
            rid = len(relations)
            relations.append(
                {
                    "id": rid,
                    "from_id": from_id,
                    "to_id": to_id,
                    "type": BLIND_TYPE if args.blind else row["label"],
                }
            )
            pairs.append(
                {
                    "relation_id": rid,
                    "candidate_id": cand.candidate_id,
                    "pathway": cand.pathway_key,
                    "disease": cand.disease_key,
                    "stratum": cand.stratum,
                    "model_label": row["label"],
                    "model_confidence": row.get("confidence", ""),
                    "model_evidence": list(as_quotes(row.get("evidence"))),
                }
            )
            stats[row["label"]] += 1

        docs.append(
            {
                "text": abstract,
                "entities": entities,
                "relations": relations,
                # pmid is written twice on purpose: the existing importer in the
                # doccano workspace reads it at top level, the exporter writes it
                # under meta, and which one survives a round-trip is unverified.
                "pmid": pmid,
                "meta": {
                    "pmid": pmid,
                    "source": str(args.relations.name),
                    "blind": args.blind,
                    "pairs": pairs,
                },
            }
        )
        stats["entities"] += len(entities)

    if args.sample:
        docs = docs[: args.sample]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")

    summary = {
        "relations_in": str(args.relations),
        "candidates": str(args.candidates),
        "blind": args.blind,
        "n_documents": len(docs),
        "n_relations": sum(len(d["relations"]) for d in docs),
        "n_entities": sum(len(d["entities"]) for d in docs),
        "relation_types": {k: v for k, v in stats.most_common() if k != "entities"},
        "out": str(args.out),
    }
    print(json.dumps(summary, indent=2))
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
