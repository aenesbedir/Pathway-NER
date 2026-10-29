#!/usr/bin/env python3
"""
generate_mesh_forms.py

Derives new pathway surface forms from MeSH entry terms, instead of only using
MeSH to check the hand-written ones.

Two generators:

  descriptor  For a canonical that is itself a MeSH descriptor, every entry term
              of that descriptor is a surface form.
                  citric acid cycle -> Krebs Cycle, Tricarboxylic Acid Cycle
  substance   For a canonical of the shape "<substance> <process>", every entry
              term of the *substance* descriptor composes with the process word.
                  vitamin a metabolism -> retinol metabolism, vitamin a1 metabolism

Entry terms are written for indexing, not for reading, so most of them are
useless as surface forms: brand names (Aquasol A, Tryptacin), IUPAC strings
("3,7-dimethyl-9-(2,6,6-trimethyl-...)"), and inverted forms ("Glutathione,
Reduced"). ``plausible()`` keeps only what could appear in an abstract, and the
corpus filter then keeps only what actually does — a form that never occurs in
10,125 abstracts adds nothing but risk.

The output is a reviewable Python table, not an edit: candidates are printed in
the same shape as MANUAL_FORMS so they can be inspected before anything is
pasted into preprocessing/pathway_surface_forms.py. Every line carries its MeSH
provenance, so a reviewer sees which descriptor vouches for it.

Inputs:
  data/raw/mesh_substances.json          (pubmed_api/fetch_mesh_substances.py)
  data/raw/mesh_metabolic_pathways.json  (pubmed_api/fetch_mesh_pathways.py)
  data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl  (corpus filter)

Run from the repository root:
    venv310/bin/python3 scripts/generate_mesh_forms.py
    venv310/bin/python3 scripts/generate_mesh_forms.py --min-occurrences 0
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "preprocessing"))
sys.path.insert(0, str(REPO_ROOT / "pubmed_api"))

from fetch_mesh_substances import components_of, substance_of  # noqa: E402
from pathway_surface_forms import (  # noqa: E402
    FORM_BLOCKLIST,
    PROCESS_WORDS,
    _strip_process_tail,
    build_surface_forms,
)

MESH_SUBSTANCE_FILE = REPO_ROOT / "data/raw/mesh_substances.json"
MESH_PATHWAY_FILE = REPO_ROOT / "data/raw/mesh_metabolic_pathways.json"
CORPUS_FILE = REPO_ROOT / "data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl"

# An entry term worth composing into a surface form: words a person would write
# in an abstract. Rejects IUPAC names, registry numbers and inverted headings.
_REJECT = re.compile(
    r"""
      \d                    # any digit: registry numbers, IUPAC locants, "Vitamin A1"
    | ,                     # inverted heading: "Glutathione, Reduced"
    | [()\[\]]              # chemical parentheses
    | \b[a-z]{1,2}-[A-Z]    # stereo/position prefixes: gamma-L-Glu, all-E
    """,
    re.VERBOSE,
)


def plausible(term: str) -> bool:
    """True when an entry term could plausibly be written in an abstract."""
    if _REJECT.search(term):
        return False
    words = term.split()
    if not 1 <= len(words) <= 4:
        return False
    if len(term) < 4:
        return False
    return True


def token_key(s: str) -> str:
    words = re.sub(r"[^a-z0-9+]+", " ", s.lower()).split()
    return " ".join(sorted(re.sub(r"s$", "", w) if len(w) > 3 else w for w in words))


def load_corpus_blob() -> str:
    texts = [json.loads(l)["text"] for l in CORPUS_FILE.open(encoding="utf-8")]
    return "\n".join(texts).lower()


def mesh_pathway_index() -> dict[str, dict]:
    """token_key of a descriptor name -> that descriptor record."""
    index = {}
    for rec in json.loads(MESH_PATHWAY_FILE.read_text(encoding="utf-8")):
        index.setdefault(token_key(rec["name"]), rec)
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--min-occurrences", type=int, default=1,
                    help="drop candidates occurring fewer times in the corpus (default 1)")
    args = ap.parse_args()

    substances = json.loads(MESH_SUBSTANCE_FILE.read_text(encoding="utf-8"))
    pathways = mesh_pathway_index()
    blob = load_corpus_blob()

    existing = {
        f.text.lower()
        for items in build_surface_forms().values()
        for f in items
    }

    candidates: dict[str, list[dict]] = collections.defaultdict(list)
    seen: set[str] = set()

    for canonical in build_surface_forms():
        head, processes = _strip_process_tail(canonical)

        # Generator 1: the canonical is itself a MeSH descriptor.
        desc = pathways.get(token_key(canonical))
        if desc:
            for term in desc["entry_terms"]:
                if plausible(term):
                    candidates[canonical].append(
                        {"form": term.lower(), "source": f"mesh:{desc['name']}",
                         "generator": "descriptor"}
                    )

        # Generator 2: compose the substance's entry terms with the process word.
        if processes:
            process = processes[-1]
            for component in components_of(head):
                sub = substances.get(component)
                if not sub:
                    continue
                for term in sub.get("entry_terms", []):
                    if plausible(term):
                        candidates[canonical].append(
                            {"form": f"{term.lower()} {process}",
                             "source": f"mesh:{sub['name']}",
                             "generator": "substance"}
                        )

    # Filter: not already present, not blocklisted, occurs in the corpus.
    kept: dict[str, list[dict]] = collections.defaultdict(list)
    dropped = collections.Counter()
    for canonical, items in candidates.items():
        for c in items:
            form = c["form"]
            if form in existing:
                dropped["already in dictionary"] += 1
                continue
            if form in seen:
                dropped["duplicate candidate"] += 1
                continue
            if token_key(form) in {token_key(b) for b in FORM_BLOCKLIST}:
                dropped["blocklisted"] += 1
                continue
            n = len(re.findall(rf"(?<![\w-]){re.escape(form)}(?![\w-])", blob))
            if n < args.min_occurrences:
                dropped["absent from corpus"] += 1
                continue
            seen.add(form)
            c["corpus_occurrences"] = n
            kept[canonical].append(c)

    total = sum(len(v) for v in kept.values())
    print(f"# {total} new surface forms derived from MeSH entry terms")
    print(f"# dropped: {dict(dropped)}")
    print("\nMESH_ENTRY_FORMS: dict[str, list[str]] = {")
    for canonical in sorted(kept, key=lambda c: -sum(i["corpus_occurrences"] for i in kept[c])):
        items = sorted(kept[canonical], key=lambda i: -i["corpus_occurrences"])
        print(f'    "{canonical}": [')
        for c in items:
            print(f'        "{c["form"]}",  # {c["corpus_occurrences"]}x  {c["source"]}  ({c["generator"]})')
        print("    ],")
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
