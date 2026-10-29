#!/usr/bin/env python3
"""
fetch_mesh_pathways.py

Fetches metabolic-process descriptors and their entry terms from MeSH via NCBI
E-utilities, to ground preprocessing/pathway_surface_forms.py in a citable
vocabulary instead of hand-written domain knowledge.

MeSH entry terms are the synonym list NLM maintains for each descriptor. They
settle questions the repo cannot settle on its own — "Krebs Cycle" and
"Tricarboxylic Acid Cycle" are entry terms of Citric Acid Cycle, so those forms
are grounded; "Respiratory Chain" is an entry term of *Electron Transport*, a
descriptor distinct from Oxidative Phosphorylation, so assigning it to the
oxidative phosphorylation canonical is a judgement MeSH does not support.

Trees fetched (all under Phenomena and Processes):
    G03  Metabolism      — includes G03.191 carbohydrate, G03.295 energy
                           metabolism, G03.493 metabolic networks and pathways
    G02.111  Biochemical Phenomena — several pathway descriptors are filed here
                           as well; harmless overlap, deduplicated by mesh_id

Strategy mirrors pubmed_api/fetch_mesh_diseases.py:
  1. ESearch: term=<tree>.*[Tree Number] -> numeric NCBI MeSH UIDs
  2. EFetch in batches -> plain-text descriptor records
  3. Parse name, entry terms, tree numbers
  4. Save as JSON list

Parsing note: the plain-text EFetch format appends the descriptor's tree *paths*
after the entry-term block, as indented lines that look identical to entry terms
("All MeSH Categories", "Phenomena and Processes Category", "Metabolism", ...).
fetch_mesh_diseases.py's parser swallows them; this one stops the entry-term
block at the first "All MeSH Categories" line, so the output holds real synonyms
only.

Output: data/raw/mesh_metabolic_pathways.json
Cache:  data/raw/mesh_cache/   (shared with fetch_mesh_diseases.py)

Run with:
    cd /home/enes/NER-pipeline
    venv310/bin/python3 pubmed_api/fetch_mesh_pathways.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path

import requests

FALLBACK_API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
API_KEY = os.environ.get("NCBI_API_KEY", FALLBACK_API_KEY)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CACHE_DIR = Path("data/raw/mesh_cache")
OUTPUT_FILE = Path("data/raw/mesh_metabolic_pathways.json")

TREES = ["G03", "G02.111"]

BATCH_SIZE = 100
SLEEP_BETWEEN = 0.34  # ~3 req/s with an API key

# The breadcrumb block that follows the entry terms in the plain-text format.
BREADCRUMB_START = "All MeSH Categories"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def esearch_mesh_tree(tree_prefix: str) -> list[str]:
    """All numeric NCBI MeSH UIDs under a tree prefix."""
    cache_file = CACHE_DIR / f"esearch_{tree_prefix.replace('.', '_')}_ids.json"
    if cache_file.exists():
        ids = json.loads(cache_file.read_text())
        log.info("Loaded %d MeSH UIDs from cache (%s)", len(ids), tree_prefix)
        return ids

    resp = requests.get(
        f"{BASE_URL}/esearch.fcgi",
        params={
            "db": "mesh",
            "term": f"{tree_prefix}.*[Tree Number]",
            "retmax": 5000,
            "retmode": "json",
            "api_key": API_KEY,
        },
        timeout=30,
    )
    resp.raise_for_status()
    ids = resp.json()["esearchresult"]["idlist"]
    log.info("ESearch %s returned %d UIDs", tree_prefix, len(ids))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(ids))
    time.sleep(SLEEP_BETWEEN)
    return ids


def efetch_mesh_batch(ids: list[str]) -> str:
    """Plain-text descriptor records for a batch of UIDs."""
    cache_file = CACHE_DIR / f"efetch_{'_'.join(ids[:3])}_n{len(ids)}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    resp = requests.get(
        f"{BASE_URL}/efetch.fcgi",
        params={"db": "mesh", "id": ",".join(ids), "retmode": "text", "api_key": API_KEY},
        timeout=60,
    )
    resp.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(resp.text, encoding="utf-8")
    time.sleep(SLEEP_BETWEEN)
    return resp.text


def parse_mesh_text(text: str, ncbi_ids: list[str]) -> list[dict]:
    """Parse EFetch plain text into {mesh_id, name, entry_terms, tree_numbers}.

    Entry terms end at the tree-path breadcrumb block; see the module docstring.
    """
    record_pattern = re.compile(r"^\d+: .+", re.MULTILINE)
    boundaries = [(m.start(), m.group()) for m in record_pattern.finditer(text)]

    records = []
    for i, (start, _header) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        lines = text[start:end].splitlines()

        name_match = re.match(r"^\d+: (.+)", lines[0])
        if not name_match:
            continue
        name = name_match.group(1).strip()

        tree_numbers: list[str] = []
        for line in lines:
            if line.startswith("Tree Number(s):"):
                raw = line[len("Tree Number(s):"):].strip()
                tree_numbers = [t.strip() for t in raw.split(",") if t.strip()]
                break

        entry_terms: list[str] = []
        in_entry_terms = False
        for line in lines:
            if line.strip() == "Entry Terms:":
                in_entry_terms = True
                continue
            if not in_entry_terms:
                continue
            stripped = line.strip()
            if stripped == BREADCRUMB_START:
                break                      # tree paths start here, not synonyms
            if line.startswith(("    ", "\t")):
                if stripped and stripped.lower() != name.lower():
                    entry_terms.append(stripped)
            elif stripped == "":
                continue
            else:
                in_entry_terms = False

        records.append({
            "mesh_id": ncbi_ids[i] if i < len(ncbi_ids) else "",
            "name": name,
            "entry_terms": list(dict.fromkeys(entry_terms)),
            "tree_numbers": tree_numbers,
        })
    return records


def fetch_tree(tree_prefix: str) -> list[dict]:
    ids = esearch_mesh_tree(tree_prefix)
    if not ids:
        log.warning("No UIDs for tree %s", tree_prefix)
        return []
    records = []
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i : i + BATCH_SIZE]
        records.extend(parse_mesh_text(efetch_mesh_batch(batch), batch))
        log.info("  %s: processed %d / %d", tree_prefix, i + len(batch), len(ids))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--output", type=Path, default=OUTPUT_FILE)
    ap.add_argument("--trees", nargs="+", default=TREES)
    args = ap.parse_args()

    by_id: dict[str, dict] = {}
    for tree in args.trees:
        for rec in fetch_tree(tree):
            by_id.setdefault(rec["mesh_id"], rec)

    records = sorted(by_id.values(), key=lambda r: r["name"].lower())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    n_terms = sum(len(r["entry_terms"]) for r in records)
    log.info("Wrote %s: %d descriptors, %d entry terms", args.output, len(records), n_terms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
