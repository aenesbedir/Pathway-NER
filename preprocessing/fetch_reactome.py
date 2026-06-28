#!/usr/bin/env python3
"""
fetch_reactome.py  —  Step 1b

Fetches all human metabolic pathway entries from Reactome.

Strategy:
  1. Download two bulk text files (cached) to build the full pathway hierarchy:
       ReactomePathways.txt       — stId, name, species
       ReactomePathwaysRelation.txt — parent stId, child stId
  2. Walk the hierarchy from the Metabolism root (R-HSA-1430728) to collect
     all descendant pathway IDs.
  3. For each pathway, call /data/query/{stId} to get name synonyms and PMIDs.

Each output record contains:
  pathway_id     : Reactome stable ID e.g. "R-HSA-77289"
  canonical_name : first entry in the pathway's name array
  synonyms       : remaining entries in the name array
  pathway_class  : "Metabolism"
  pmids          : PubMed IDs from literatureReference fields
  source         : "reactome"

Output : data/raw/reactome_pathways.jsonl
Cache  : data/raw/reactome_cache/
"""

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REACTOME_BASE = "https://reactome.org/ContentService"
REACTOME_DOWNLOAD = "https://reactome.org/download/current"
METABOLISM_ROOT = "R-HSA-1430728"
REQUEST_DELAY = 0.1
OUTPUT_FILE = Path("data/raw/reactome_pathways.jsonl")
CACHE_DIR = Path("data/raw/reactome_cache")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------
def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "NER-pipeline/1.0 (research)",
    })
    return session


def fetch_text(
    session: requests.Session, url: str, cache_path: Path
) -> str:
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    resp = session.get(url, timeout=60, headers={"Accept": "text/plain"})
    resp.raise_for_status()
    text = resp.text
    cache_path.write_text(text, encoding="utf-8")
    time.sleep(REQUEST_DELAY)
    return text


def fetch_json(
    session: requests.Session, url: str, cache_path: Path
) -> any:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(REQUEST_DELAY)
    return data


# ---------------------------------------------------------------------------
# Hierarchy helpers
# ---------------------------------------------------------------------------
def load_human_pathways(session: requests.Session) -> dict[str, str]:
    """Returns {stId: name} for all Homo sapiens pathways."""
    text = fetch_text(
        session,
        f"{REACTOME_DOWNLOAD}/ReactomePathways.txt",
        CACHE_DIR / "ReactomePathways.txt",
    )
    pathways: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[2].strip() == "Homo sapiens":
            pathways[parts[0].strip()] = parts[1].strip()
    return pathways


def load_hierarchy(session: requests.Session) -> dict[str, list[str]]:
    """Returns {parent_stId: [child_stId, ...]} for all Reactome pathways."""
    text = fetch_text(
        session,
        f"{REACTOME_DOWNLOAD}/ReactomePathwaysRelation.txt",
        CACHE_DIR / "ReactomePathwaysRelation.txt",
    )
    children: dict[str, list[str]] = defaultdict(list)
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            parent, child = parts[0].strip(), parts[1].strip()
            children[parent].append(child)
    return dict(children)


def collect_descendants(
    root: str,
    children: dict[str, list[str]],
    human_ids: set[str],
) -> list[str]:
    """BFS from root; returns all descendant IDs that are human pathways."""
    result: list[str] = []
    queue: list[str] = [root]
    visited: set[str] = set()
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        if node in human_ids:
            result.append(node)
        for child in children.get(node, []):
            if child not in visited:
                queue.append(child)
    return result


# ---------------------------------------------------------------------------
# Detail fetch & parsing
# ---------------------------------------------------------------------------
def fetch_pathway_detail(session: requests.Session, st_id: str) -> Optional[dict]:
    cache_path = CACHE_DIR / f"{st_id}.json"
    try:
        return fetch_json(session, f"{REACTOME_BASE}/data/query/{st_id}", cache_path)
    except requests.HTTPError as exc:
        log.warning("HTTP error for %s: %s", st_id, exc)
        return None


def parse_record(detail: dict, fallback_name: str) -> dict:
    raw_names: list[str] = detail.get("name", [])
    if isinstance(raw_names, str):
        raw_names = [raw_names]

    canonical = raw_names[0] if raw_names else fallback_name

    seen: set[str] = {canonical.lower()}
    synonyms: list[str] = []
    for n in raw_names[1:]:
        if n.lower() not in seen:
            seen.add(n.lower())
            synonyms.append(n)

    pmids: list[str] = []
    for ref in detail.get("literatureReference", []):
        pmid = ref.get("pubMedIdentifier")
        if pmid and str(pmid).isdigit():
            pmids.append(str(pmid))
    pmids = list(dict.fromkeys(pmids))

    return {
        "pathway_id": detail.get("stId", ""),
        "canonical_name": canonical,
        "synonyms": synonyms,
        "pathway_class": "Metabolism",
        "pmids": pmids,
        "source": "reactome",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    session = build_session()

    # -- 1. Build hierarchy from bulk files ------------------------------------
    log.info("Loading human pathway list …")
    human_pathways = load_human_pathways(session)
    log.info("Human pathways in Reactome: %d", len(human_pathways))

    log.info("Loading pathway hierarchy …")
    children_map = load_hierarchy(session)

    # -- 2. Collect all metabolic pathway IDs ----------------------------------
    human_ids = set(human_pathways.keys())
    metabolic_ids = collect_descendants(METABOLISM_ROOT, children_map, human_ids)
    log.info(
        "Metabolic pathways under %s: %d", METABOLISM_ROOT, len(metabolic_ids)
    )

    # -- 3. Fetch detail for each pathway --------------------------------------
    records: list[dict] = []
    failed: list[str] = []

    for st_id in tqdm(metabolic_ids, desc="Fetching pathway details", unit="pw"):
        detail = fetch_pathway_detail(session, st_id)
        if detail is None:
            failed.append(st_id)
            continue
        fallback = human_pathways.get(st_id, st_id)
        records.append(parse_record(detail, fallback))

    # -- 4. Write output -------------------------------------------------------
    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    # -- 5. Summary stats ------------------------------------------------------
    total_pmids = sum(len(r["pmids"]) for r in records)
    with_pmids = sum(1 for r in records if r["pmids"])
    avg_pmids = total_pmids / len(records) if records else 0

    log.info("─" * 60)
    log.info("Output         : %s", OUTPUT_FILE)
    log.info("Pathways saved : %d", len(records))
    log.info("Failed fetches : %d", len(failed))
    log.info("With ≥1 PMID   : %d / %d", with_pmids, len(records))
    log.info("Total PMIDs    : %d  (avg %.1f per pathway)", total_pmids, avg_pmids)
    log.info("─" * 60)

    if failed:
        log.warning("Failed IDs: %s", failed)


if __name__ == "__main__":
    main()
