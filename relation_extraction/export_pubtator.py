#!/usr/bin/env python3
"""
export_pubtator.py

Write candidate pairs as a PubTator file so an off-the-shelf BioRED relation
extractor (BioREx / BioREDirect) can be run over them without retraining.

What this test can and cannot answer
------------------------------------
Neither model knows a `PATHWAY` entity type. Their entity vocabulary is
ChemicalEntity, DiseaseOrPhenotypicFeature, GeneOrGeneProduct, SequenceVariant,
and the type pair is fed to the model as a soft prompt
(`src/data_processor.py: considered_ne_pairs`), so an unknown type is not simply
ignored - it lands in the out-of-vocabulary bucket. The pathway side is therefore
masked as `GeneOrGeneProduct`, which makes the pair
`(GeneOrGeneProduct, DiseaseOrPhenotypicFeature)`: a real type pair, and BioRED's
largest relation class. `reports/relation_extraction_independent_review_2026-08-19.md`
§1a-bis proposed exactly this surrogate.

The output labels map onto v3 as:

    Positive_Correlation -> upregulation
    Negative_Correlation -> downregulation
    Association          -> association
    None                 -> none

`Bind`, `Comparison`, `Conversion`, `Cotreatment` and `Drug_Interaction` have no
v3 counterpart; they are recorded as `unmapped` rather than folded into a class
they do not mean.

A number produced this way measures agreement with an LLM teacher on a
surrogate entity type, not accuracy against gold. It is a signal check.

Offsets
-------
PubTator gives a document a title line and an abstract line, and entity offsets
are global over `title + " " + abstract`. The corpus here stores one text field,
so the split is made at an existing space and every offset is preserved exactly.
The writer asserts this rather than assuming it.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

from schema import Candidate, normalize_surface, read_jsonl

REPO = Path(__file__).resolve().parents[1]

#: Surrogate BioRED types. The pathway side has no true counterpart; see module docstring.
PATHWAY_TYPE = "GeneOrGeneProduct"
DISEASE_TYPE = "DiseaseOrPhenotypicFeature"

BIORED_TO_V3 = {
    "Positive_Correlation": "upregulation",
    "Negative_Correlation": "downregulation",
    "Association": "association",
    "None": "none",
}


def entity_id(prefix: str, key: str) -> str:
    return prefix + ":" + re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:60]


def split_title(text: str) -> tuple[str, str]:
    """Split `text` into (title, abstract) at a space, preserving global offsets.

    PubTator reassembles the document as `title + " " + abstract`. Splitting at an
    existing space means the reassembled string equals the original, so every
    stored offset stays valid. The first sentence break is preferred; failing
    that, any space; failing that, the document is emitted with an empty abstract.
    """
    m = re.search(r"(?<=[.!?]) (?=[A-Z0-9(])", text[:400])
    idx = m.start() if m else text.find(" ", 1)
    if idx <= 0:
        return text, ""
    title, abstract = text[:idx], text[idx + 1 :]
    assert title + " " + abstract == text, "title split changed the document"
    return title, abstract


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--stratum",
        default="",
        help="restrict to one stratum, e.g. same_sentence",
    )
    args = ap.parse_args()

    cands = [Candidate.from_json(d) for d in read_jsonl(args.candidates)]
    if args.stratum:
        cands = [c for c in cands if c.stratum == args.stratum]

    by_pmid: dict[str, list[Candidate]] = defaultdict(list)
    for c in cands:
        by_pmid[c.pmid].append(c)

    n_docs = n_ann = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for pmid in sorted(by_pmid):
            group = by_pmid[pmid]
            text = group[0].abstract
            title, abstract = split_title(text)
            fh.write(f"{pmid}|t|{title}\n")
            fh.write(f"{pmid}|a|{abstract}\n")

            # One annotation line per mention, deduplicated on offsets: the same
            # mention is shared by every candidate pair that uses it.
            seen: set[tuple[int, int]] = set()
            lines: list[tuple[int, str]] = []
            for c in group:
                for m, typ, prefix, key in (
                    *[(m, PATHWAY_TYPE, "PATHWAY", c.pathway_key) for m in c.pathway_mentions],
                    *[(m, DISEASE_TYPE, "DISEASE", c.disease_key) for m in c.disease_mentions],
                ):
                    if (m.start, m.end) in seen:
                        continue
                    seen.add((m.start, m.end))
                    assert text[m.start : m.end] == m.text
                    lines.append(
                        (
                            m.start,
                            f"{pmid}\t{m.start}\t{m.end}\t{m.text}\t{typ}\t"
                            f"{entity_id(prefix, key)}",
                        )
                    )
            for _, line in sorted(lines):
                fh.write(line + "\n")
                n_ann += 1
            fh.write("\n")
            n_docs += 1

    print(
        f"{n_docs} documents, {n_ann} entity annotations, "
        f"{len(cands)} candidate pairs -> {args.out}"
    )


if __name__ == "__main__":
    main()
