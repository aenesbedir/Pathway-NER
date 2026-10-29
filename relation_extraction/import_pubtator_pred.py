#!/usr/bin/env python3
"""
import_pubtator_pred.py

Read BioREDirect's prediction table and re-express it as v3 relation records.

BioREDirect writes one score row per instance in its input TSV, in the same
order, with a header naming the columns of three heads: nine relation labels,
three novelty labels, four direction labels. Only the relation head is used here;
`direction` is BioRED's subject/object asymmetry, which v3 deliberately does not
model, and `novelty` is about whether a finding is new, not what it claims.

The label map is deliberately partial:

    Positive_Correlation -> upregulation
    Negative_Correlation -> downregulation
    Association          -> association
    None                 -> none

`Bind`, `Comparison`, `Conversion`, `Cotreatment` and `Drug_Interaction` describe
chemical and gene interactions with no pathway-disease reading. They are emitted
with label `unmapped` and counted separately rather than folded into `association`,
which would inflate agreement by turning a wrong answer into a vague one.

Pairing back to candidates goes through the entity identifiers written by
`export_pubtator.py` (`PATHWAY:<key>` / `DISEASE:<key>`), never through offsets:
the exporter shifts offsets by the length of its placeholder title and rewrites
Unicode whitespace, so offsets in the PubTator file are not the corpus offsets.

BioREDirect enumerates its own pairs from the entity identifiers in the document,
so its instance list is not the candidate list. Instances with no matching
candidate are reported as `unmatched_instances`; candidates with no instance are
reported as `candidates_without_prediction`. Neither is silently dropped.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from export_pubtator import BIORED_TO_V3, DISEASE_TYPE, PATHWAY_TYPE, entity_id
from schema import Candidate, Relation, SCHEMA_TAG, read_jsonl, write_jsonl

#: Number of columns belonging to the relation head, in header order.
N_RELATION_LABELS = 9


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--tsv", type=Path, required=True, help="converter output")
    ap.add_argument("--pred", type=Path, required=True, help="prediction scores")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--source", default="biored:bioredirect_biored_pt")
    args = ap.parse_args()

    cands = [Candidate.from_json(d) for d in read_jsonl(args.candidates)]
    by_ids: dict[tuple[str, str, str], Candidate] = {}
    for c in cands:
        key = (
            c.pmid,
            entity_id("PATHWAY", c.pathway_key),
            entity_id("DISEASE", c.disease_key),
        )
        by_ids[key] = c

    tsv_rows = [
        line.rstrip("\n").split("\t")
        for line in args.tsv.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pred_lines = args.pred.read_text(encoding="utf-8").splitlines()
    header = pred_lines[0].split("\t")
    labels = header[:N_RELATION_LABELS]
    scores = [line.split("\t") for line in pred_lines[1:] if line.strip()]

    if len(scores) != len(tsv_rows):
        raise SystemExit(
            f"{len(scores)} prediction rows for {len(tsv_rows)} instances; "
            "the two files are not aligned"
        )

    out: list[Relation] = []
    counts: Counter = Counter()
    matched_ids: set[tuple[str, str, str]] = set()

    for row, score in zip(tsv_rows, scores):
        pmid, _type1, _type2, id1, id2 = row[0], row[1], row[2], row[3], row[4]
        pathway_id = next((i for i in (id1, id2) if i.startswith("PATHWAY:")), None)
        disease_id = next((i for i in (id1, id2) if i.startswith("DISEASE:")), None)
        if pathway_id is None or disease_id is None:
            counts["instance_not_a_pathway_disease_pair"] += 1
            continue

        cand = by_ids.get((pmid, pathway_id, disease_id))
        if cand is None:
            counts["unmatched_instances"] += 1
            continue
        matched_ids.add((pmid, pathway_id, disease_id))

        values = [float(x) for x in score[:N_RELATION_LABELS]]
        best = labels[max(range(len(values)), key=values.__getitem__)]
        counts[f"biored:{best}"] += 1
        v3 = BIORED_TO_V3.get(best, "unmapped")
        if v3 == "unmapped":
            counts["unmapped_label"] += 1

        out.append(
            Relation(
                pmid=cand.pmid,
                disease=cand.disease_mentions[0],
                pathway=cand.pathway_mentions[0],
                label=v3,
                # BioREDirect returns no evidence sentence: its instance is the
                # whole document with the two entities marked.
                evidence="",
                certainty="asserted",
                confidence="medium",
                relation_source=args.source,
                candidate_id=cand.candidate_id,
                stratum=cand.stratum,
                schema=SCHEMA_TAG,
            )
        )

    counts["candidates_without_prediction"] = len(by_ids) - len(matched_ids)
    n = write_jsonl(args.out, out)

    summary = {
        "source": args.source,
        "candidates": str(args.candidates),
        "n_candidates": len(by_ids),
        "n_instances": len(tsv_rows),
        "n_rows_written": n,
        "v3_labels": dict(Counter(r.label for r in out).most_common()),
        "diagnostics": dict(counts.most_common()),
        "note": (
            "PATHWAY was masked as GeneOrGeneProduct; the model has no pathway "
            "entity type. Labels outside the v3 map are written as 'unmapped'."
        ),
    }
    args.out.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
