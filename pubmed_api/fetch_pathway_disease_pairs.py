#!/usr/bin/env python3
"""
fetch_pathway_disease_pairs.py

For each (Recon3D pathway × disease) pair, queries PubMed for co-occurring
abstracts and saves the results.

Strategy:
  - For each pair: ESearch "(pathway[Title/Abstract]) AND (disease[Title/Abstract])"
  - Collect PMIDs (capped at MAX_PMIDS_PER_PAIR per pair)
  - Save pairs JSON; article fetching is done separately by fetch_articles.py

Output:
  data/raw/pathway_disease_pairs.json  — pairs with hit PMIDs

Run with:
    cd /home/enes/NER-pipeline
    python3 pubmed_api/fetch_pathway_disease_pairs.py \
        --diseases data/raw/selected_diseases.json

Flags:
  --diseases FILE  Disease JSON file (default: data/raw/selected_diseases.json)
  --dry-run        Search only, skip abstract fetch (articles handled by fetch_articles.py)
  --top N          Limit to first N diseases (for testing)
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

PATHWAYS_FILE = Path("unique_pathways_from_recon.json")
DEFAULT_DISEASES_FILE = Path("data/raw/selected_diseases.json")
PAIRS_OUT = Path("data/raw/pathway_disease_pairs.json")
CACHE_DIR = Path("data/raw/pair_cache")

SLEEP = 0.11      # ~10 req/s with API key
MAX_PMIDS_PER_PAIR = 20   # cap to avoid flooding on very broad pairs
ABSTRACT_BATCH = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def esearch_pair(pathway: str, disease: str) -> list[str]:
    """Return up to MAX_PMIDS_PER_PAIR PMIDs for the pathway+disease co-occurrence query."""
    cache_key = re.sub(r"[^a-z0-9]", "_", f"{pathway}_{disease}".lower())[:120]
    cache_file = CACHE_DIR / f"search_{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    query = f'("{pathway}"[Title/Abstract]) AND ("{disease}"[Title/Abstract])'
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": MAX_PMIDS_PER_PAIR,
        "retmode": "json",
        "api_key": API_KEY,
    }
    resp = requests.get(f"{BASE_URL}/esearch.fcgi", params=params, timeout=30)
    resp.raise_for_status()
    pmids = resp.json()["esearchresult"]["idlist"]
    cache_file.write_text(json.dumps(pmids))
    time.sleep(SLEEP)
    return pmids



def load_pathways() -> list[str]:
    return json.loads(PATHWAYS_FILE.read_text())


def load_diseases(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--diseases",
        default=str(DEFAULT_DISEASES_FILE),
        help=f"Disease JSON file (default: {DEFAULT_DISEASES_FILE})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Search only, do not fetch abstracts")
    parser.add_argument("--top", type=int, default=None, help="Limit to first N diseases (for testing)")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PAIRS_OUT.parent.mkdir(parents=True, exist_ok=True)

    pathways = load_pathways()
    diseases = load_diseases(Path(args.diseases))
    if args.top:
        diseases = diseases[: args.top]

    log.info(
        "Diseases file: %s  |  Pathways: %d  |  Diseases: %d  |  Total pairs: %d",
        args.diseases, len(pathways), len(diseases), len(pathways) * len(diseases),
    )

    pairs_with_hits = []
    all_pmids_seen: set[str] = set()

    total_pairs = len(pathways) * len(diseases)
    done = 0
    for disease in diseases:
        for pathway in pathways:
            pmids = esearch_pair(pathway, disease["name"])
            done += 1
            if pmids:
                pairs_with_hits.append({
                    "pathway": pathway,
                    "disease_name": disease["name"],
                    "disease_mesh_id": disease["mesh_id"],
                    "disease_category": disease.get("category", ""),
                    "pmids": pmids,
                })
                all_pmids_seen.update(pmids)

            if done % 500 == 0:
                log.info(
                    "  %d / %d pairs searched  |  %d with hits  |  %d unique PMIDs",
                    done, total_pairs, len(pairs_with_hits), len(all_pmids_seen),
                )

    log.info(
        "Done. %d / %d pairs with hits. %d unique PMIDs.",
        len(pairs_with_hits), total_pairs, len(all_pmids_seen),
    )

    PAIRS_OUT.write_text(json.dumps(pairs_with_hits, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved pairs → %s", PAIRS_OUT)

    if args.dry_run:
        log.info("--dry-run: article fetch skipped (run fetch_articles.py separately)")


if __name__ == "__main__":
    main()
