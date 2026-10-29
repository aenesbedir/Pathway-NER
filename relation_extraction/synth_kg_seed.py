#!/usr/bin/env python3
"""
synth_kg_seed.py

Build (disease, pathway) seed pairs from SMPDB for KG-seeded synthetic generation.

THROWAWAY PROBE. Nothing here feeds a recorded run. The question is only whether
grounded synthetic examples can be generated at all and how many survive a blind
re-label by the teacher.

Why SMPDB and not PrimeKG
-------------------------
PrimeKG has no disease-pathway edge. It carries `disease_protein` and
`pathway_protein`, so a disease-pathway link is a two-hop inference through a
gene: high recall, low precision, and it says nothing about direction. Its
pathways are Reactome, which is signalling-heavy, while this project's v1 scope
is metabolic pathways only (`docs/superpowers/specs/...-gold-corpus-design.md`
section 2.3). HumanCyc/BioCyc data files are behind a paid subscription.

SMPDB is free, human, and metabolic. It also ships a `Disease` pathway subject
whose members are inborn errors of metabolism, each drawn as a perturbation of a
named metabolic pathway. That gives a disease-pathway pairing without the gene
hop.

How a pair is derived
---------------------
1. Every SMPDB pathway is reduced to its set of HMDB metabolite ids.
2. A `Metabolic` pathway is kept only if its name matches one of the 98 Recon
   pathway names this project can actually tag (`unique_pathways_from_recon.json`),
   by token-set Jaccard over a small synonym fold (biosynthesis -> synthesis,
   dropping `cycle`/`pathway`/`and`).
3. Each `Disease` pathway is matched to the mapped metabolic pathway with the
   highest metabolite Jaccard, above a floor.

Both steps are string and set heuristics, so the mapping is noisy by
construction: `nucleotide metabolism` matches `Nucleotide Sugars Metabolism`, and
`d-alanine metabolism` matches `Alanine Metabolism`. The seed file records the
score of every pair so the noise is visible rather than assumed away. The seed
decides only *which* pair gets written about - never its label.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RAW = REPO / "data/raw/smpdb"
DEFAULT_OUT = REPO / "data/processed/relation/synth_probe/kg_seeds.jsonl"
RECON = REPO / "unique_pathways_from_recon.json"

PATHWAYS_URL = "https://smpdb.ca/downloads/smpdb_pathways.csv.zip"
METABOLITES_URL = "https://smpdb.ca/downloads/smpdb_metabolites.csv.zip"

#: Folded before comparing pathway names. Recon writes "bile acid synthesis"
#: where SMPDB writes "Bile Acid Biosynthesis"; "cycle" and "pathway" are
#: decoration on one side only.
NAME_SYNONYMS = {"biosynthesis": "synthesis", "cycle": "", "pathway": "", "and": "", "the": ""}


def fetch(url: str, dest: Path) -> Path:
    """Download `url` to `dest` once. Existing files are never re-fetched."""
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=600) as resp:
        dest.write_bytes(resp.read())
    return dest


def name_tokens(name: str) -> frozenset[str]:
    words = (NAME_SYNONYMS.get(w, w) for w in re.split(r"[^a-z0-9]+", name.lower()) if w)
    return frozenset(w for w in words if w)


def read_metabolite_sets(zip_path: Path) -> dict[str, tuple[str, set[str]]]:
    """(pathway name, subject) -> HMDB id set, read straight from the archive."""
    out: dict[tuple[str, str], set[str]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if not info.filename.endswith("_metabolites.csv"):
                continue
            with zf.open(info) as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"))
                for row in reader:
                    hmdb = (row.get("HMDB ID") or "").strip()
                    if not hmdb:
                        continue
                    key = (row["Pathway Name"], row["Pathway Subject"])
                    out.setdefault(key, set()).add(hmdb)
    return out


def map_metabolic_to_recon(names: list[str], recon: list[str], floor: float) -> dict[str, list[str]]:
    """SMPDB metabolic pathway name -> the Recon names it plausibly denotes."""
    recon_tokens = {r: name_tokens(r) for r in recon}
    mapping: dict[str, list[str]] = {}
    for name in names:
        nt = name_tokens(name)
        if not nt:
            continue
        hits = []
        for r, rt in recon_tokens.items():
            if not rt:
                continue
            j = len(nt & rt) / len(nt | rt)
            if j >= floor:
                hits.append((r, round(j, 3)))
        if hits:
            mapping[name] = hits
    return mapping


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--name-floor", type=float, default=0.6,
                    help="token Jaccard for SMPDB metabolic name -> Recon name")
    ap.add_argument("--metabolite-floor", type=float, default=0.30,
                    help="metabolite Jaccard for disease pathway -> metabolic pathway")
    args = ap.parse_args()

    fetch(PATHWAYS_URL, args.raw_dir / "smpdb_pathways.csv.zip")
    met_zip = fetch(METABOLITES_URL, args.raw_dir / "smpdb_metabolites.csv.zip")

    recon = json.loads(RECON.read_text())
    sets = read_metabolite_sets(met_zip)
    metabolic = {n: ids for (n, subj), ids in sets.items() if subj == "Metabolic"}
    disease = {n: ids for (n, subj), ids in sets.items() if subj == "Disease"}

    mapping = map_metabolic_to_recon(sorted(metabolic), recon, args.name_floor)
    metabolic = {n: ids for n, ids in metabolic.items() if n in mapping}
    print(
        f"{len(sets)} SMPDB pathways with metabolites; "
        f"{len(metabolic)} metabolic pathways map to {len({r for v in mapping.values() for r, _ in v})}"
        f"/{len(recon)} Recon names; {len(disease)} disease pathways",
        file=sys.stderr,
    )

    rows = []
    for dname, dids in disease.items():
        best, best_j = None, 0.0
        for mname, mids in metabolic.items():
            inter = len(dids & mids)
            if not inter:
                continue
            j = inter / len(dids | mids)
            if j > best_j:
                best_j, best = j, mname
        if best is None or best_j < args.metabolite_floor:
            continue
        for recon_name, name_j in sorted(mapping[best]):
            rows.append(
                {
                    "disease": dname,
                    "smpdb_pathway": best,
                    "recon_pathway": recon_name,
                    "metabolite_jaccard": round(best_j, 3),
                    "name_jaccard": name_j,
                    "source": "smpdb",
                }
            )

    rows.sort(key=lambda r: (-r["metabolite_jaccard"], r["disease"], r["recon_pathway"]))
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
