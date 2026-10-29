#!/usr/bin/env python3
"""
synth_counterfactual.py

Produce direction-flipped counterfactual abstracts from existing silver labels.

THROWAWAY PROBE. See `synth_kg_seed.py` for the framing.

The idea
--------
`upregulation` and `downregulation` differ from each other by a small closed set
of polarity words, and by nothing else. An abstract whose evidence sentence says
"markedly increased" becomes a valid `downregulation` example the moment that
phrase becomes "markedly decreased" - the entities, the syntax, the hedging and
the sentence position are all preserved. So the flip manufactures examples of the
rare direction classes without asking a model to invent biology, which is where
generation is least trustworthy.

What is generated is an abstract, not a label: the flipped text is written out as
a `Candidate`, and the label it actually carries is decided by re-running
`run_teacher.py` over it blind. The deterministic flip only supplies the
*expected* label the re-labelling is scored against.

Discipline
----------
A rewrite is emitted only when it is unambiguous:

- exactly one polarity term occurs in the evidence sentence, so the flip has one
  reading;
- the term does not overlap a disease or pathway mention, so no entity surface is
  rewritten;
- the entity offsets are shifted by the length delta of the replacement, and the
  resulting candidate is re-validated against the schema before being kept.

Everything rejected is counted by reason. A high rejection rate is a finding
about the method, not a bug to be smoothed over.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from schema import (
    Candidate,
    Mention,
    RecordError,
    candidate_id,
    read_jsonl,
    write_jsonl,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INDIR = REPO / "data/processed/relation/silver_2k"
DEFAULT_OUT = REPO / "data/processed/relation/synth_probe/counterfactual"

#: Polarity terms that carry the direction of a pathway-disease claim, paired
#: with their opposite. Matched case-insensitively on whole words; the
#: replacement copies the casing pattern of what it replaces.
#:
#: Deliberately small. Every entry is a term whose reversal flips the claim and
#: nothing else. Words like "altered" or "dysregulated" are absent because they
#: are unsigned - they belong to `association`, and flipping them would be
#: inventing a direction the sentence never had.
FLIPS = [
    ("increased", "decreased"),
    ("increase", "decrease"),
    ("increases", "decreases"),
    ("elevated", "reduced"),
    ("elevation", "reduction"),
    ("upregulated", "downregulated"),
    ("upregulation", "downregulation"),
    ("up-regulated", "down-regulated"),
    ("up-regulation", "down-regulation"),
    ("overexpressed", "underexpressed"),
    ("overexpression", "underexpression"),
    ("activated", "inhibited"),
    ("activation", "inhibition"),
    ("enhanced", "suppressed"),
    ("enhancement", "suppression"),
    ("induced", "repressed"),
    ("induction", "repression"),
    ("accumulation", "depletion"),
    ("higher", "lower"),
    ("high", "low"),
    ("stimulated", "impaired"),
    ("gain", "loss"),
]

OPPOSITE = {}
for a, b in FLIPS:
    OPPOSITE[a] = b
    OPPOSITE[b] = a

TERM_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(t) for t in OPPOSITE), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

FLIP_LABEL = {"upregulation": "downregulation", "downregulation": "upregulation"}


def match_case(source: str, replacement: str) -> str:
    """Give `replacement` the casing of `source`. Only the cases that occur."""
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def shift(mention: Mention, at: int, delta: int) -> Mention:
    """Move a mention that starts after an edit at `at` by `delta` characters."""
    if mention.start < at:
        return mention
    return Mention(mention.text, mention.start + delta, mention.end + delta, mention.label)


def flip_one(
    cand: Candidate, evidence: str, rejected: collections.Counter
) -> tuple[Candidate, str] | None:
    """Rewrite the one polarity term in `evidence`, returning the new candidate."""
    abstract = cand.abstract
    ev_at = abstract.find(evidence)
    if ev_at < 0:
        rejected["evidence_not_in_abstract"] += 1
        return None

    hits = list(TERM_RE.finditer(evidence))
    if not hits:
        rejected["no_polarity_term"] += 1
        return None
    if len(hits) > 1:
        rejected["ambiguous_multiple_terms"] += 1
        return None

    hit = hits[0]
    at = ev_at + hit.start()
    end = ev_at + hit.end()

    spans = [(m.start, m.end) for m in (*cand.pathway_mentions, *cand.disease_mentions)]
    if any(at < s_end and s_start < end for s_start, s_end in spans):
        rejected["term_inside_entity"] += 1
        return None

    new_text = match_case(hit.group(0), OPPOSITE[hit.group(0).lower()])
    new_abstract = abstract[:at] + new_text + abstract[end:]
    delta = len(new_text) - (end - at)

    pmid = f"CF{cand.candidate_id}"
    new = Candidate(
        candidate_id=candidate_id(pmid, cand.pathway_key, cand.disease_key),
        pmid=pmid,
        abstract=new_abstract,
        pathway_key=cand.pathway_key,
        disease_key=cand.disease_key,
        pathway_mentions=[shift(m, at, delta) for m in cand.pathway_mentions],
        disease_mentions=[shift(m, at, delta) for m in cand.disease_mentions],
        # The sentence index is not recomputed after the edit, and a stale span
        # would be a lie about the text. The stratum is dropped to doc_level,
        # which the schema allows to carry no shared sentence.
        shared_sentences=[],
        stratum="doc_level",
        pathway_variants=list(cand.pathway_variants),
        disease_variants=list(cand.disease_variants),
    )
    try:
        new.check()
    except RecordError as exc:
        rejected[f"schema_invalid:{exc}"[:60]] += 1
        return None
    return new, new_abstract[at : at + len(new_text)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--indir", type=Path, default=DEFAULT_INDIR)
    ap.add_argument("--relations", type=Path, default=None)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0, help="stop after N flips")
    args = ap.parse_args()

    rel_path = args.relations or (args.indir / "relations_llm_opus.jsonl")
    cands = {c.candidate_id: c for c in (Candidate.from_json(d) for d in read_jsonl(args.indir / "candidates.jsonl"))}
    rels = read_jsonl(rel_path)

    rejected: collections.Counter = collections.Counter()
    out_cands: list[Candidate] = []
    expected: list[dict] = []
    seen: set[str] = set()

    for r in rels:
        if r["label"] not in FLIP_LABEL:
            continue
        cand = cands.get(r.get("candidate_id", ""))
        if cand is None:
            rejected["candidate_not_found"] += 1
            continue
        if cand.candidate_id in seen:
            rejected["duplicate_candidate"] += 1
            continue
        made = flip_one(cand, r.get("evidence", ""), rejected)
        if made is None:
            continue
        new, flipped_term = made
        seen.add(cand.candidate_id)
        out_cands.append(new)
        expected.append(
            {
                "candidate_id": new.candidate_id,
                "pmid": new.pmid,
                "expected_label": FLIP_LABEL[r["label"]],
                "source_label": r["label"],
                "source_pmid": r["pmid"],
                "source_candidate_id": cand.candidate_id,
                "flipped_to": flipped_term,
                "method": "counterfactual",
            }
        )
        if args.limit and len(out_cands) >= args.limit:
            break

    args.outdir.mkdir(parents=True, exist_ok=True)
    n = write_jsonl(args.outdir / "candidates.jsonl", out_cands)
    write_jsonl(args.outdir / "expected.jsonl", expected)

    summary = {
        "method": "counterfactual",
        "source_relations": str(rel_path),
        "n_signed_rows": sum(1 for r in rels if r["label"] in FLIP_LABEL),
        "n_generated": n,
        "expected_labels": dict(
            collections.Counter(e["expected_label"] for e in expected).most_common()
        ),
        "rejected": dict(rejected.most_common()),
        "outdir": str(args.outdir),
    }
    (args.outdir / "generation.summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
