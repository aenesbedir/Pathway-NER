#!/usr/bin/env python3
"""
fetch_mesh_diseases.py

Fetches all disease terms from the MeSH C18 subtree
(Metabolic and Nutritional Diseases) via NCBI E-utilities.

Strategy:
  1. ESearch: term=C18.*[Tree Number] → list of numeric NCBI MeSH UIDs
  2. EFetch in batches → plain-text descriptor records
  3. Parse name, entry terms (synonyms), tree numbers
  4. Save as JSON list

Output: data/raw/mesh_c18_diseases.json
Cache:  data/raw/mesh_cache/

Run with:
    cd /home/enes/NER-pipeline
    python3 pubmed_api/fetch_mesh_diseases.py
"""

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

BATCH_SIZE = 100
SLEEP_BETWEEN = 0.34  # ~3 req/s with API key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def esearch_mesh_tree(tree_prefix: str) -> list[str]:
    """Return all numeric NCBI MeSH UIDs under a given tree prefix."""
    cache_key = tree_prefix.replace(".", "_")
    cache_file = CACHE_DIR / f"esearch_{cache_key}_ids.json"
    if cache_file.exists():
        ids = json.loads(cache_file.read_text())
        log.info("Loaded %d MeSH UIDs from cache (%s)", len(ids), tree_prefix)
        return ids

    url = f"{BASE_URL}/esearch.fcgi"
    params = {
        "db": "mesh",
        "term": f"{tree_prefix}.*[Tree Number]",
        "retmax": 5000,
        "retmode": "json",
        "api_key": API_KEY,
    }
    log.info("ESearch: querying MeSH %s subtree...", tree_prefix)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    ids = data["esearchresult"]["idlist"]
    log.info("ESearch %s returned %d UIDs", tree_prefix, len(ids))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(ids))
    return ids


def efetch_mesh_batch(ids: list[str]) -> str:
    """Fetch plain-text descriptor records for a batch of NCBI MeSH UIDs."""
    cache_key = f"efetch_{'_'.join(ids[:3])}_n{len(ids)}.txt"
    cache_file = CACHE_DIR / cache_key

    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    url = f"{BASE_URL}/efetch.fcgi"
    params = {
        "db": "mesh",
        "id": ",".join(ids),
        "retmode": "text",
        "api_key": API_KEY,
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    text = resp.text
    cache_file.write_text(text, encoding="utf-8")
    return text


def parse_mesh_text(text: str, ncbi_ids: list[str]) -> list[dict]:
    """
    Parse NCBI MeSH plain-text EFetch output into structured records.

    Text format per record:
        N: DescriptorName
        <description paragraphs>
        Tree Number(s): C18.xxx, C16.xxx
        Entry Terms:
            synonym1
            synonym2
    Records are numbered sequentially and separated by blank lines before
    the next "N+1:" header.
    """
    # Split on record boundaries: lines like "1: Name", "2: Name", etc.
    record_pattern = re.compile(r"^\d+: .+", re.MULTILINE)
    boundaries = [(m.start(), m.group()) for m in record_pattern.finditer(text)]

    records = []
    for i, (start, header) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        block = text[start:end]
        lines = block.splitlines()

        # First line: "N: Name"
        name_match = re.match(r"^\d+: (.+)", lines[0])
        if not name_match:
            continue
        name = name_match.group(1).strip()

        # Tree numbers
        tree_numbers = []
        for line in lines:
            if line.startswith("Tree Number(s):"):
                raw = line[len("Tree Number(s):"):].strip()
                tree_numbers = [t.strip() for t in raw.split(",") if t.strip()]
                break

        # Entry terms (synonyms): indented lines after "Entry Terms:" header
        synonyms = []
        in_entry_terms = False
        for line in lines:
            if line.strip() == "Entry Terms:":
                in_entry_terms = True
                continue
            if in_entry_terms:
                if line.startswith("    ") or line.startswith("\t"):
                    term = line.strip()
                    if term and term.lower() != name.lower():
                        synonyms.append(term)
                elif line.strip() == "":
                    continue
                else:
                    # New section header — stop
                    in_entry_terms = False

        ncbi_uid = ncbi_ids[i] if i < len(ncbi_ids) else ""
        records.append({
            "mesh_id": ncbi_uid,
            "name": name,
            "synonyms": list(dict.fromkeys(synonyms)),
            "tree_numbers": tree_numbers,
        })

    return records


def fetch_tree(tree_prefix: str) -> list[dict]:
    """Fetch and parse all MeSH descriptors under a tree prefix."""
    ids = esearch_mesh_tree(tree_prefix)
    if not ids:
        log.warning("No UIDs for tree %s", tree_prefix)
        return []

    records = []
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i : i + BATCH_SIZE]
        text = efetch_mesh_batch(batch_ids)
        parsed = parse_mesh_text(text, batch_ids)
        records.extend(parsed)
        log.info("  %s: processed %d / %d", tree_prefix, i + len(batch_ids), len(ids))
        time.sleep(SLEEP_BETWEEN)

    filtered = [d for d in records if any(tn.startswith(tree_prefix) for tn in d["tree_numbers"])]
    log.info("Tree %s: fetched %d, filtered to %d with matching tree number", tree_prefix, len(records), len(filtered))
    return filtered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trees",
        nargs="+",
        default=["C18"],
        help="MeSH tree prefixes to fetch (e.g. C18 C04 C10.574). Default: C18",
    )
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for stale in CACHE_DIR.glob("efetch_*.xml"):
        stale.unlink()

    all_diseases = []
    seen_ids: set[str] = set()

    for tree in args.trees:
        diseases = fetch_tree(tree)
        for d in diseases:
            if d["mesh_id"] not in seen_ids:
                seen_ids.add(d["mesh_id"])
                all_diseases.append(d)

    log.info("Total unique diseases across trees %s: %d", args.trees, len(all_diseases))

    # Save one file per tree prefix + combined
    for tree in args.trees:
        tree_diseases = [d for d in all_diseases if any(tn.startswith(tree) for tn in d["tree_numbers"])]
        safe = tree.replace(".", "_")
        out = Path(f"data/raw/mesh_{safe}_diseases.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(tree_diseases, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Saved %d diseases → %s", len(tree_diseases), out)

    if len(args.trees) > 1:
        combined_out = Path("data/raw/mesh_all_diseases.json")
        combined_out.write_text(json.dumps(all_diseases, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Saved %d combined diseases → %s", len(all_diseases), combined_out)

    log.info("Sample entries:")
    for d in all_diseases[:5]:
        log.info("  [%s] %s  (%d synonyms)  trees: %s", d["mesh_id"], d["name"], len(d["synonyms"]), d["tree_numbers"][:2])


if __name__ == "__main__":
    main()
