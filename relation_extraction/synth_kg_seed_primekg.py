#!/usr/bin/env python3
"""
synth_kg_seed_primekg.py

Build (disease, pathway) seed pairs from PrimeKG by a two-hop walk through genes.

THROWAWAY PROBE. Companion to `synth_kg_seed.py`, which does the same job from
SMPDB. Neither feeds a recorded run.

Why this exists
---------------
The SMPDB seeds cover 135 diseases, all inborn errors of metabolism, because the
only disease-pathway pairing SMPDB offers is its `Disease` pathway subject. Real
PubMed is dominated by common disease. PrimeKG was rejected earlier as a *label*
source - its edges are undirected, so it cannot supply `upregulation` or
`downregulation` - but seed selection is not labelling. For the job the KG
actually does here, deciding which pair gets written about, the two-hop walk is
worth measuring rather than assuming away.

The walk
--------
    disease --(disease, gene/protein edge)--> gene <--(pathway, gene/protein edge)-- pathway

PrimeKG collapses genes and their products into one `gene/protein` node type, so
both hops land on the same node set. Edges are discovered by their endpoint
types rather than by relation name, so a change in PrimeKG's naming does not
silently produce an empty graph.

Scoring
-------
Gene-set Jaccard, the same measure `synth_kg_seed.py` applies to metabolite sets,
so the two seed files are comparable. Jaccard is harsh on large pathways: a
pathway with 400 genes cannot score highly against a disease with 20. The raw
intersection size is therefore recorded alongside it, and `--rank-by` chooses
which one orders the candidates.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

from synth_kg_seed import name_tokens

REPO = Path(__file__).resolve().parents[1]
DEFAULT_KG = REPO / "data/raw/primekg/kg.csv"
DEFAULT_OUT = REPO / "data/processed/relation/synth_probe/kg_seeds_primekg.jsonl"
RECON = REPO / "unique_pathways_from_recon.json"

DISEASE = "disease"
PATHWAY = "pathway"
GENE = "gene/protein"


def read_edges(kg: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], collections.Counter]:
    """disease -> gene ids, pathway -> gene ids, plus the relation names seen.

    Rows are selected by endpoint type, in either column order, because PrimeKG
    stores each edge once per direction and the relation names carry no reliable
    order convention.
    """
    disease: dict[str, set[str]] = collections.defaultdict(set)
    pathway: dict[str, set[str]] = collections.defaultdict(set)
    relations: collections.Counter = collections.Counter()

    with open(kg, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            xt, yt = row["x_type"], row["y_type"]
            if xt == GENE and yt in (DISEASE, PATHWAY):
                gene, name, owner_type = row["x_index"], row["y_name"], yt
            elif yt == GENE and xt in (DISEASE, PATHWAY):
                gene, name, owner_type = row["y_index"], row["x_name"], xt
            else:
                continue
            (disease if owner_type == DISEASE else pathway)[name].add(gene)
            relations[(row["relation"], xt, yt)] += 1
    return dict(disease), dict(pathway), relations


def map_pathways_to_recon(names, recon: list[str], floor: float) -> dict[str, list[tuple[str, float]]]:
    """PrimeKG (Reactome) pathway name -> the Recon names it plausibly denotes."""
    recon_tokens = {r: name_tokens(r) for r in recon}
    mapping: dict[str, list[tuple[str, float]]] = {}
    for name in names:
        nt = name_tokens(name)
        if not nt:
            continue
        hits = [
            (r, round(len(nt & rt) / len(nt | rt), 3))
            for r, rt in recon_tokens.items()
            if rt and len(nt & rt) / len(nt | rt) >= floor
        ]
        if hits:
            mapping[name] = hits
    return mapping


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kg", type=Path, default=DEFAULT_KG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--name-floor", type=float, default=0.6,
                    help="token Jaccard for PrimeKG pathway name -> Recon name")
    ap.add_argument("--gene-floor", type=float, default=0.0,
                    help="gene-set Jaccard floor for a disease -> pathway pair")
    ap.add_argument("--min-shared", type=int, default=3,
                    help="minimum shared genes for a pair to be emitted")
    ap.add_argument("--rank-by", choices=("jaccard", "shared"), default="jaccard")
    ap.add_argument("--per-disease", type=int, default=1,
                    help="pairs kept per disease, best first")
    args = ap.parse_args()

    recon = json.loads(RECON.read_text())
    disease, pathway, relations = read_edges(args.kg)
    print(f"{len(disease)} diseases, {len(pathway)} pathways with genes", file=sys.stderr)
    for (rel, xt, yt), n in relations.most_common():
        print(f"  edge {rel:<20} {xt} -> {yt}  n={n}", file=sys.stderr)

    mapping = map_pathways_to_recon(sorted(pathway), recon, args.name_floor)
    pathway = {n: g for n, g in pathway.items() if n in mapping}
    reachable = {r for v in mapping.values() for r, _ in v}
    print(
        f"{len(pathway)} PrimeKG pathways map to {len(reachable)}/{len(recon)} Recon names",
        file=sys.stderr,
    )

    rows = []
    for dname, dgenes in disease.items():
        scored = []
        for pname, pgenes in pathway.items():
            shared = len(dgenes & pgenes)
            if shared < args.min_shared:
                continue
            j = shared / len(dgenes | pgenes)
            if j < args.gene_floor:
                continue
            scored.append((j, shared, pname))
        if not scored:
            continue
        scored.sort(key=lambda t: (t[0] if args.rank_by == "jaccard" else t[1]), reverse=True)
        for j, shared, pname in scored[: args.per_disease]:
            for recon_name, name_j in sorted(mapping[pname]):
                rows.append(
                    {
                        "disease": dname,
                        "kg_pathway": pname,
                        "recon_pathway": recon_name,
                        "gene_jaccard": round(j, 4),
                        "shared_genes": shared,
                        "disease_genes": len(dgenes),
                        "name_jaccard": name_j,
                        "source": "primekg",
                    }
                )

    rows.sort(key=lambda r: (-r["gene_jaccard"], r["disease"], r["recon_pathway"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "n_seeds": len(rows),
                "n_diseases": len({r["disease"] for r in rows}),
                "n_recon_pathways": len({r["recon_pathway"] for r in rows}),
                "top_pathways": collections.Counter(
                    r["recon_pathway"] for r in rows
                ).most_common(10),
                "output": str(args.out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
