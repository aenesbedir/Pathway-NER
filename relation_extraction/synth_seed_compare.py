#!/usr/bin/env python3
"""
synth_seed_compare.py

Compare seed sources by whether real literature actually discusses the pairs
they propose.

THROWAWAY PROBE. See `synth_kg_seed.py` for the framing.

Why not acceptance rate
-----------------------
The obvious comparison - generate from each seed source and score the blind
re-label - cannot separate them. Acceptance measures whether the generator can
be steered to a requested class, and it saturated at 0.979 on the SMPDB seeds.
A generator told to write `downregulation` about an absurd pair will still write
`downregulation`; the filter passes it and the number says nothing about the
pair.

What a seed source is actually for is choosing pairs a paper might plausibly be
written about. That is checkable directly, against the 10k real abstracts in
`data/processed/pathway-10k/articles.jsonl`: how often do the two names of a
proposed pair appear in the same abstract?

The permutation control
-----------------------
A raw co-occurrence rate confounds two things: whether the pairing is good, and
whether the disease is one PubMed writes about at all. A source drawing on rare
inborn errors of metabolism is penalised for its vocabulary, not its pairing.

So each source is scored against its own permutation: the same diseases and the
same pathways, re-paired at random. The lift over that control is the part
attributable to the pairing. A source whose real pairs co-occur no more often
than its shuffled pairs is contributing nothing a random assignment would not.

Matching is deliberately crude - case-folded substring, no normalisation beyond
dropping a trailing parenthetical. It is applied identically to every source, so
it understates all of them equally.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = REPO / "data/processed/pathway-10k/articles.jsonl"


def short_name(name: str) -> str:
    """Case-folded surface, minus a trailing parenthetical abbreviation."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip().lower()


def load_corpus(path: Path) -> list[str]:
    """Abstracts, case-folded.

    Some records carry a raw newline inside the abstract string, so a record is
    not always a line. Scanning line by line and joining until the buffer parses
    loses every record after the first one it cannot close - it silently read
    6,700 of 10,125 abstracts - so the file is decoded as a stream of
    concatenated JSON values instead.
    """
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        row, i = decoder.raw_decode(text, i)
        out.append(row["abstract"].lower())
    return out


def presence(terms: set[str], corpus: list[str]) -> dict[str, set[int]]:
    """term -> indices of the abstracts containing it, by substring."""
    hits: dict[str, set[int]] = {t: set() for t in terms}
    for i, text in enumerate(corpus):
        for t in terms:
            if t in text:
                hits[t].add(i)
    return hits


def score(pairs: list[tuple[str, str]], hits: dict[str, set[int]]) -> dict:
    """Attestation counts for one list of (disease surface, pathway surface)."""
    d_seen = p_seen = both = 0
    for d, p in pairs:
        dh, ph = hits.get(d, set()), hits.get(p, set())
        d_seen += bool(dh)
        p_seen += bool(ph)
        both += bool(dh & ph)
    n = len(pairs)
    eligible = sum(1 for d, p in pairs if hits.get(d) and hits.get(p))
    return {
        "n_pairs": n,
        "disease_attested": round(d_seen / n, 3) if n else 0.0,
        "pathway_attested": round(p_seen / n, 3) if n else 0.0,
        "co_occurring": round(both / n, 3) if n else 0.0,
        # Both names have to be in the corpus at all before their co-occurrence
        # says anything about the pairing.
        "co_occurring_given_both_present": round(both / eligible, 3) if eligible else 0.0,
        "n_both_present": eligible,
    }


def permute(pairs: list[tuple[str, str]], seed: int) -> list[tuple[str, str]]:
    """Same diseases, same pathways, re-paired at random."""
    rng = random.Random(seed)
    pathways = [p for _, p in pairs]
    rng.shuffle(pathways)
    return [(d, p) for (d, _), p in zip(pairs, pathways)]


def read_source(path: Path) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out.append((short_name(row["disease"]), row["recon_pathway"].strip().lower()))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", metavar="LABEL=PATH", required=True,
                    help="seed file to score; repeatable")
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--permutations", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    sources = {}
    for spec in args.source:
        label, _, path = spec.partition("=")
        sources[label] = read_source(Path(path))

    corpus = load_corpus(args.corpus)
    terms = {t for pairs in sources.values() for pair in pairs for t in pair}
    print(f"{len(corpus)} abstracts, {len(terms)} distinct surfaces", file=sys.stderr)
    hits = presence(terms, corpus)

    report = {"corpus": str(args.corpus), "n_abstracts": len(corpus), "sources": {}}
    for label, pairs in sources.items():
        real = score(pairs, hits)
        controls = [score(permute(pairs, s), hits) for s in range(args.permutations)]
        mean = lambda k: round(sum(c[k] for c in controls) / len(controls), 3)  # noqa: E731
        report["sources"][label] = {
            **real,
            "n_diseases": len({d for d, _ in pairs}),
            "n_pathways": len({p for _, p in pairs}),
            "permuted_co_occurring": mean("co_occurring"),
            "permuted_co_occurring_given_both_present": mean("co_occurring_given_both_present"),
            "lift": round(
                real["co_occurring_given_both_present"]
                - mean("co_occurring_given_both_present"),
                3,
            ),
            "top_pathways": collections.Counter(p for _, p in pairs).most_common(5),
        }

    labels = list(sources)
    if len(labels) > 1:
        overlap = {}
        for i, a in enumerate(labels):
            for b in labels[i + 1:]:
                sa, sb = set(sources[a]), set(sources[b])
                overlap[f"{a}&{b}"] = {
                    "shared_pairs": len(sa & sb),
                    "shared_diseases": len({d for d, _ in sa} & {d for d, _ in sb}),
                }
        report["overlap"] = overlap

    out = args.out or (REPO / "data/processed/relation/synth_probe/seed_compare.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
