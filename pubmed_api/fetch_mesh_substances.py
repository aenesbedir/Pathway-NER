#!/usr/bin/env python3
"""
fetch_mesh_substances.py

Resolves the substance half of every pathway surface form to a MeSH descriptor,
so that forms of the shape "<substance> <process>" can be grounded even though
MeSH has no descriptor for most of them.

Why this is needed: MeSH does not name "tryptophan metabolism" as a descriptor.
It names the substance (Tryptophan, D014364) and expresses the process as the
/metabolism qualifier attached to it. Recon canonicals, by contrast, are written
as "<substance> metabolism" throughout. So the two vocabularies can only be
compared by decomposing our forms and comparing the substances:

    "retinol metabolism"    -> retinol  -> MeSH: Vitamin A
    "vitamin a metabolism"  -> vitamin a -> MeSH: Vitamin A     => same concept

That is a citable statement from NLM that the two forms name one thing, which is
exactly what preprocessing/pathway_surface_forms.py's hand-written MANUAL_FORMS
lacked.

The lookup uses the [MeSH Terms] field, which resolves entry terms to their
descriptor: "cobalamin" returns Vitamin B 12, "retinol" returns Vitamin A. A
substance with no descriptor (abbreviations like "trp", "gsh", "bcaa") returns
nothing and stays ungrounded — reported, not guessed.

Two spelling conventions differ systematically between Recon and MeSH, so each
substance is tried in a few variants and the one that matched is recorded in
``matched_variant``:

  plural    MeSH files compound classes in the plural — "purine" is Purines,
            "pyrimidine" is Pyrimidines.
  acid/salt Recon writes the conjugate base, MeSH the acid — "arachidonate" is
            Arachidonic Acid, "ascorbate" is Ascorbic Acid.

Multi-substance strings ("alanine and aspartate", "glycine, serine, alanine, and
threonine") have no descriptor of their own and are split on connectors, so each
component is resolved separately. That is what lets a split form such as
"proline metabolism" be compared against "arginine and proline metabolism".

Tree numbers are stored alongside the descriptor. Two substances landing on
different descriptors are not necessarily in conflict: MeSH tree numbers say
whether one is an ancestor of the other, which separates "ceramide is a kind of
sphingolipid" from "glutamine is not glutamate".

Input : the substance strings extracted from preprocessing/pathway_surface_forms.py
Entry terms are stored too. They are the reason this file is worth having twice
over: besides settling whether a hand-written form is right, the entry terms of a
substance descriptor *generate* forms nobody thought of. Vitamin A carries
Retinol and Vitamin A1, so "retinol metabolism" and "vitamin a1 metabolism" are
both derivable for the vitamin a metabolism canonical, with NLM as the source.

Output: data/raw/mesh_substances.json
        {substance: {mesh_id, name, tree_numbers, entry_terms} | null}
Cache : data/raw/mesh_cache/substance_<slug>.json  (one file per lookup)

Run with:
    cd /home/enes/NER-pipeline
    venv310/bin/python3 pubmed_api/fetch_mesh_substances.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "preprocessing"))

from pathway_surface_forms import (  # noqa: E402
    PROCESS_WORDS,
    _strip_process_tail,
    build_surface_forms,
)

FALLBACK_API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
API_KEY = os.environ.get("NCBI_API_KEY", FALLBACK_API_KEY)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CACHE_DIR = REPO_ROOT / "data/raw/mesh_cache"
OUTPUT_FILE = REPO_ROOT / "data/raw/mesh_substances.json"
SLEEP_BETWEEN = 0.34  # ~3 req/s with an API key

_PROCESS_RE = "|".join(re.escape(p) for p in PROCESS_WORDS)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def substance_of(text: str) -> str | None:
    """The substance half of '<substance> <process>', or None if not that shape.

    Peels *every* trailing process word, not just the last one: the substance of
    "androgen and estrogen synthesis and metabolism" is "androgen and estrogen",
    not "androgen and estrogen synthesis and".
    """
    head, processes = _strip_process_tail(text)
    return head if processes and head else None


_CONNECTOR = re.compile(r"\s+and\s+|\s*,\s*|\s*/\s*")


def components_of(substance: str) -> list[str]:
    """['alanine', 'aspartate'] for 'alanine and aspartate'; [s] when single."""
    parts = []
    for part in _CONNECTOR.split(substance):
        part = re.sub(r"^(?:and|or)\s+", "", part.strip()).strip()
        if len(part) >= 3:
            parts.append(part)
    return parts if len(parts) > 1 else [substance]


def variants_of(substance: str) -> list[str]:
    """Spelling variants to try, most faithful first."""
    out = [substance]
    if not substance.endswith("s"):
        out.append(substance + "s")
    if substance.endswith("ate"):
        out.append(substance[:-3] + "ic acid")
    return out


def collect_substances() -> list[str]:
    """Every distinct substance string in the dictionary, plus their components."""
    found: set[str] = set()
    for canonical, items in build_surface_forms().items():
        for text in [canonical, *(f.text for f in items)]:
            s = substance_of(text)
            if not s:
                continue
            found.add(s)
            found.update(components_of(s))
    return sorted(found)


BREADCRUMB_START = "All MeSH Categories"


def parse_entry_terms(text: str, name: str) -> list[str]:
    """The 'Entry Terms:' block, stopping before the tree-path breadcrumbs.

    Same trap as in fetch_mesh_pathways.py: the plain-text format lists the
    descriptor's tree paths right after the entry terms, indented identically.
    """
    terms: list[str] = []
    in_block = False
    for line in text.splitlines():
        if line.strip() == "Entry Terms:":
            in_block = True
            continue
        if not in_block:
            continue
        stripped = line.strip()
        if stripped == BREADCRUMB_START:
            break
        if line.startswith(("    ", "\t")):
            if stripped and stripped.lower() != name.lower():
                terms.append(stripped)
        elif stripped:
            in_block = False
    return list(dict.fromkeys(terms))


def parse_tree_numbers(text: str) -> list[str]:
    """The 'Tree Number(s):' line of a plain-text descriptor record."""
    m = re.search(r"^Tree Number\(s\): (.+)$", text, re.M)
    return [t.strip() for t in m.group(1).split(",") if t.strip()] if m else []


def refetch(mesh_id: str, name: str) -> dict:
    """Tree numbers and entry terms for one descriptor, to top up cache entries."""
    txt = requests.get(
        f"{BASE_URL}/efetch.fcgi",
        params={"db": "mesh", "id": mesh_id, "retmode": "text", "api_key": API_KEY},
        timeout=30,
    ).text
    time.sleep(SLEEP_BETWEEN)
    return {
        "tree_numbers": parse_tree_numbers(txt),
        "entry_terms": parse_entry_terms(txt, name),
    }


def lookup(substance: str) -> dict | None:
    """Resolve one substance to its MeSH descriptor, or None."""
    slug = re.sub(r"[^a-z0-9]+", "_", substance.lower()).strip("_")[:80]
    # v2: the cache key changed meaning when variant lookups were added, so a
    # miss recorded under the old key is not a miss under the new rules.
    cache_file = CACHE_DIR / f"substance2_{slug}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        # Entries written before tree numbers were collected are topped up in
        # place; only the efetch is repeated, never the esearch.
        if cached is None or "entry_terms" in cached:
            return cached
        cached.update(refetch(cached["mesh_id"], cached["name"]))
        cache_file.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")
        return cached

    result = None
    for variant in variants_of(substance):
        resp = requests.get(
            f"{BASE_URL}/esearch.fcgi",
            params={
                "db": "mesh",
                "term": f'"{variant}"[MeSH Terms]',
                "retmax": 3,
                "retmode": "json",
                "api_key": API_KEY,
            },
            timeout=30,
        )
        resp.raise_for_status()
        ids = resp.json()["esearchresult"]["idlist"]
        time.sleep(SLEEP_BETWEEN)
        if not ids:
            continue

        txt = requests.get(
            f"{BASE_URL}/efetch.fcgi",
            params={"db": "mesh", "id": ids[0], "retmode": "text", "api_key": API_KEY},
            timeout=30,
        ).text
        time.sleep(SLEEP_BETWEEN)
        names = re.findall(r"^\d+: (.+)$", txt, re.M)
        if names:
            name = names[0].strip()
            result = {
                "mesh_id": ids[0],
                "name": name,
                "tree_numbers": parse_tree_numbers(txt),
                "entry_terms": parse_entry_terms(txt, name),
                "matched_variant": variant,
            }
            break

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--output", type=Path, default=OUTPUT_FILE)
    ap.add_argument("--limit", type=int, help="resolve only the first N substances")
    args = ap.parse_args()

    substances = collect_substances()
    if args.limit:
        substances = substances[: args.limit]
    log.info("Resolving %d substance strings against MeSH", len(substances))

    resolved: dict[str, dict | None] = {}
    for i, s in enumerate(substances, 1):
        resolved[s] = lookup(s)
        if i % 25 == 0:
            hits = sum(1 for v in resolved.values() if v)
            log.info("  %d / %d  (%d resolved)", i, len(substances), hits)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(resolved, indent=2, ensure_ascii=False), encoding="utf-8")

    hits = sum(1 for v in resolved.values() if v)
    log.info("Wrote %s: %d substances, %d resolved to a descriptor",
             args.output, len(resolved), hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
