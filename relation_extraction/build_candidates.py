#!/usr/bin/env python3
"""
build_candidates.py

Turn a sample of the pathway-10k corpus into normalized (pathway, disease)
candidate pairs for relation labelling.

Source and its bias
-------------------
`docs/superpowers/specs/2026-08-16-relation-extraction-gold-corpus-design.md` §4.1
rejects this corpus for the *gold* sample: it was collected through canonical
pathway x disease PubMed queries, so running the pipeline on it preserves that
selection bias. That objection is about measuring deployment prevalence, and it
still stands for the gold panels.

This script builds a *silver teacher* set, where the same objection has less
force: the point is to give a student encoder many labelled pairs, not to
estimate how often a relation occurs in unseen PubMed. The bias is recorded in
the manifest (`retrieval_source: canonical_query_10k`) so that no downstream
report can quietly present a number from this pool as a prevalence estimate. Gold
still has to come from disease-only retrieval.

Sampling is restricted to the *train* split of
`data/processed/pathway-10k/splits.json`. The 1,012 validation and 1,013 test
PMIDs are never touched, so a later gold set drawn from them stays clean of any
abstract the teacher has already seen.

Strata
------
`same_sentence`
    Both entities appear together in at least one sentence. Every such pair is
    emitted. This is where nearly all stated relations live.

`doc_level`
    The two entities never share a sentence. These are emitted as a random
    sample, not exhaustively: the full product is roughly six times the
    same-sentence set and is overwhelmingly `none`. Without them the teacher and
    the student would only ever see pairs that are already likely positive, the
    `none` class would be unlearnable, and the model would assign a relation to
    every pair it is shown.

Sentence segmentation uses spaCy's rule-based `sentencizer` over the exact stored
abstract, as the design spec requires. Its version is recorded in the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

import spacy

from schema import (
    Candidate,
    Mention,
    SCHEMA_VERSION,
    candidate_id,
    normalize_surface,
    write_jsonl,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = REPO / "data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl"
DEFAULT_SPLITS = REPO / "data/processed/pathway-10k/splits.json"
DEFAULT_OUTDIR = REPO / "data/processed/relation/silver_2k"

RETRIEVAL_SOURCE = "canonical_query_10k"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sentencizer():
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def sentence_spans(nlp, text: str) -> list[tuple[int, int]]:
    doc = nlp(text)
    return [(s.start_char, s.end_char) for s in doc.sents]


def group_mentions(labels, text, wanted):
    """Group one document's spans of type `wanted` by normalized surface."""
    groups: dict[str, list[Mention]] = defaultdict(list)
    for start, end, label in labels:
        if label != wanted:
            continue
        surface = text[start:end]
        groups[normalize_surface(surface)].append(
            Mention(text=surface, start=start, end=end, label=label)
        )
    for key in groups:
        groups[key].sort(key=lambda m: m.start)
    return groups


def build_for_document(nlp, pmid: str, text: str, labels) -> list[Candidate]:
    pathways = group_mentions(labels, text, "PATHWAY")
    diseases = group_mentions(labels, text, "DISEASE")
    if not pathways or not diseases:
        return []

    sents = sentence_spans(nlp, text)

    def sentence_index(offset: int) -> int:
        for i, (s, e) in enumerate(sents):
            if s <= offset < e:
                return i
        return -1

    p_sents = {k: {sentence_index(m.start) for m in ms} for k, ms in pathways.items()}
    d_sents = {k: {sentence_index(m.start) for m in ms} for k, ms in diseases.items()}

    out: list[Candidate] = []
    for pkey, pms in sorted(pathways.items()):
        for dkey, dms in sorted(diseases.items()):
            shared = sorted(i for i in p_sents[pkey] & d_sents[dkey] if i >= 0)
            cand = Candidate(
                candidate_id=candidate_id(pmid, pkey, dkey),
                pmid=pmid,
                abstract=text,
                pathway_key=pkey,
                disease_key=dkey,
                pathway_mentions=pms,
                disease_mentions=dms,
                shared_sentences=[sents[i] for i in shared],
                stratum="same_sentence" if shared else "doc_level",
            )
            cand.check()
            out.append(cand)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    ap.add_argument(
        "--pmids",
        type=Path,
        default=None,
        help="label exactly these PMIDs (one per line) instead of sampling the train split",
    )
    ap.add_argument(
        "--pathway-source",
        type=Path,
        default=None,
        help=(
            "take PATHWAY spans from this doccano file instead of --corpus, keeping "
            "DISEASE spans from --corpus. Used when a human-reviewed pathway layer "
            "exists for the same PMIDs, as it does for gt_100."
        ),
    )
    ap.add_argument("--n-docs", type=int, default=2000)
    ap.add_argument(
        "--n-doc-level",
        type=int,
        default=1800,
        help="how many doc_level candidates to keep (same_sentence is exhaustive)",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.pmids:
        sample = {l.strip() for l in args.pmids.read_text().splitlines() if l.strip()}
        selection = f"explicit list: {args.pmids}"
    else:
        splits = json.loads(args.splits.read_text())
        train = sorted(str(p) for p in splits["train"])
        rng = random.Random(args.seed)
        sample = set(rng.sample(train, args.n_docs))
        selection = "random sample of the train split"

    #: PMID -> PATHWAY spans, when a separate reviewed pathway layer is supplied.
    pathway_override: dict[str, list] = {}
    if args.pathway_source:
        for line in args.pathway_source.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            meta = rec.get("meta") or {}
            pmid = str(meta.get("pmid", rec.get("id")))
            spans = rec.get("label")
            if spans is None:  # doccano export with `entities`
                spans = [
                    [e["start_offset"], e["end_offset"], e["label"]]
                    for e in rec.get("entities", [])
                ]
            pathway_override[pmid] = [s for s in spans if s[2] == "PATHWAY"]

    nlp = load_sentencizer()
    same, doc_level = [], []
    docs_seen = docs_with_pairs = 0

    with open(args.corpus, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            pmid = str(rec["meta"].get("pmid"))
            if pmid not in sample:
                continue
            docs_seen += 1
            labels = rec["label"]
            if pathway_override:
                labels = [s for s in labels if s[2] != "PATHWAY"] + pathway_override.get(pmid, [])
            cands = build_for_document(nlp, pmid, rec["text"], labels)
            if cands:
                docs_with_pairs += 1
            for c in cands:
                (same if c.stratum == "same_sentence" else doc_level).append(c)

    if docs_seen != len(sample):
        missing = len(sample) - docs_seen
        raise SystemExit(f"{missing} selected PMIDs are absent from {args.corpus}")

    doc_level.sort(key=lambda c: c.candidate_id)
    kept_doc_level = (
        doc_level
        if args.n_doc_level >= len(doc_level)
        else random.Random(args.seed + 1).sample(doc_level, args.n_doc_level)
    )
    kept_doc_level.sort(key=lambda c: (c.pmid, c.candidate_id))
    same.sort(key=lambda c: (c.pmid, c.candidate_id))

    args.outdir.mkdir(parents=True, exist_ok=True)
    out_path = args.outdir / "candidates.jsonl"
    n = write_jsonl(out_path, [*same, *kept_doc_level])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "retrieval_source": RETRIEVAL_SOURCE,
        "bias_note": (
            "PMIDs originate from canonical pathway x disease PubMed queries. "
            "Counts from this pool are not deployment prevalence estimates."
        ),
        "corpus": str(args.corpus),
        "corpus_sha256": sha256_file(args.corpus),
        "splits": str(args.splits),
        "splits_sha256": sha256_file(args.splits),
        "split_used": "train" if not args.pmids else "explicit",
        "selection": selection,
        "pathway_source": str(args.pathway_source) if args.pathway_source else None,
        "seed": args.seed,
        "n_docs_requested": args.n_docs,
        "n_docs_found": docs_seen,
        "n_docs_with_candidates": docs_with_pairs,
        "n_same_sentence": len(same),
        "n_doc_level_total": len(doc_level),
        "n_doc_level_kept": len(kept_doc_level),
        "n_candidates": n,
        "spacy_version": spacy.__version__,
        "segmentation": "spacy.blank('en') + sentencizer",
        "output": str(out_path),
        "output_sha256": sha256_file(out_path),
    }
    (args.outdir / "candidates.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
