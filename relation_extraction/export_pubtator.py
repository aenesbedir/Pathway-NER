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


#: Placeholder title. See `split_title`.
SYNTHETIC_TITLE = "Abstract"
TITLE_SHIFT = len(SYNTHETIC_TITLE) + 1

#: PubTator delimits its title and abstract lines with `|` and the reader takes
#: the third field, so an abstract containing a pipe is silently truncated there
#: and every later offset in that document lands outside the text. Substituting a
#: single same-width character keeps all offsets exact and costs one glyph; the
#: alternative, dropping the document, loses it from the comparison entirely.
PIPE_SUBSTITUTE = "/"

#: BioREDirect maps an entity's character offsets onto BERT tokens by counting
#: characters with ASCII spaces removed
#: (`src/dataset_format_converter/utils.py: tokenize_document_by_bert`). The
#: tokenizer, however, drops every kind of Unicode whitespace, so a non-breaking
#: or thin space desynchronises the two counts and the entity after it can no
#: longer be located - the converter then aborts the file. These abstracts carry
#: 129 non-breaking and 63 thin spaces, so the substitution is not optional.
#: Every replacement is one character for one character, leaving offsets exact.
UNICODE_SPACES = "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000\u200b\ufeff"
SPACE_TABLE = {ord(ch): " " for ch in UNICODE_SPACES}


def sanitize(text: str) -> str:
    """Replace pipes and Unicode whitespace, one character for one character."""
    return text.replace("|", PIPE_SUBSTITUTE).translate(SPACE_TABLE)


def split_title(text: str) -> tuple[str, str, int]:
    """Return (title, abstract, offset shift) for a document with no stored title.

    PubTator reassembles a document as `title + " " + abstract` and requires every
    annotation to fall entirely inside one of the two passages. Splitting the
    stored text at its first sentence break satisfies the offsets but not that
    second rule: this corpus has entity spans that begin in the first sentence and
    end after it, and BioREDirect's reader aborts the whole file when one
    annotation cannot be assigned to a passage.

    A fixed placeholder title avoids the boundary entirely - the real text becomes
    the abstract, whole - at the price of shifting every offset by a constant. The
    shift is returned rather than applied silently, and the mapping back to
    candidates goes through entity identifiers, not offsets.
    """
    return SYNTHETIC_TITLE, text, TITLE_SHIFT


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

    n_docs = n_ann = n_piped = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for pmid in sorted(by_pmid):
            group = by_pmid[pmid]
            text = group[0].abstract
            clean = sanitize(text)
            if clean != text:
                n_piped += 1
            text = clean
            title, abstract, shift = split_title(text)
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
                    a, b = m.start + shift, m.end + shift
                    doc = title + " " + abstract
                    surface = doc[a:b]
                    assert len(surface) == len(m.text), (
                        "shifted offset does not span the mention"
                    )
                    assert surface == sanitize(m.text), (
                        "shifted offset does not land on the mention"
                    )
                    lines.append(
                        (
                            a,
                            f"{pmid}\t{a}\t{b}\t{surface}\t{typ}\t"
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
    if n_piped:
        print(f"  {n_piped} documents were sanitized (pipe / Unicode whitespace)")


if __name__ == "__main__":
    main()
