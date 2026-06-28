#!/usr/bin/env python3
"""
fetch_kegg.py  —  Step 1a

Fetches all human metabolic pathway entries from the KEGG REST API.
Each output record contains:
  pathway_id     : e.g. "hsa00010"
  canonical_name : e.g. "Glycolysis / Gluconeogenesis"
  synonyms       : e.g. ["Glycolysis", "Gluconeogenesis"]
  pathway_class  : e.g. "Metabolism; Carbohydrate metabolism"
  pmids          : list of PubMed IDs referenced in the pathway entry
  source         : "kegg"

Output : data/raw/kegg_pathways.jsonl
Cache  : data/raw/kegg_cache/  (raw API responses — enables safe resume)

Usage:
  python fetch_kegg.py            # metabolism pathways only (default)
  python fetch_kegg.py --all      # all pathway classes
"""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KEGG_BASE = "https://rest.kegg.jp"
ORGANISM = "hsa"
REQUEST_DELAY = 0.35          # ~3 req/s — within KEGG's recommended limit
OUTPUT_FILE = Path("data/raw/kegg_pathways.jsonl")
CACHE_DIR = Path("data/raw/kegg_cache")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP session with retry/backoff
# ---------------------------------------------------------------------------
def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=6,
        backoff_factor=2,               # 2, 4, 8, 16, 32, 64 s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = "NER-pipeline/1.0 (research; elifyrtkrn@gmail.com)"
    return session


def fetch_text(
    session: requests.Session,
    url: str,
    cache_path: Optional[Path] = None,
) -> str:
    """GET url, optionally reading from / writing to a local cache file."""
    if cache_path and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    response = session.get(url, timeout=30)
    response.raise_for_status()
    text = response.text

    if cache_path:
        cache_path.write_text(text, encoding="utf-8")

    time.sleep(REQUEST_DELAY)
    return text


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_pathway_list(text: str) -> list[tuple[str, str]]:
    """
    Parse the /list/pathway/hsa response.

    Each line:  path:hsa00010\tGlycolysis / Gluconeogenesis - Homo sapiens (human)
    Returns:    [("hsa00010", "Glycolysis / Gluconeogenesis"), ...]
    """
    pathways = []
    for line in text.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        pathway_id = parts[0].strip().removeprefix("path:")
        name = parts[1].strip()
        # Drop " - Homo sapiens (human)" suffix
        if " - Homo sapiens" in name:
            name = name[: name.index(" - Homo sapiens")].strip()
        pathways.append((pathway_id, name))
    return pathways


def parse_pathway_entry(text: str) -> dict:
    """
    Parse a KEGG flat-file pathway entry into a structured dict.

    KEGG flat-file layout:
      Columns 0-11  : section key (left-aligned, space-padded)
      Columns 12+   : value
      Lines starting with whitespace are continuations of the previous section.
      '///' marks end-of-record.
    """
    result: dict = {
        "canonical_name": "",
        "synonyms": [],
        "pathway_class": "",
        "pmids": [],
    }
    current_section = ""

    for line in text.splitlines():
        if line.startswith("///"):
            break

        if line and not line[0].isspace():
            current_section = line[:12].strip()
            value = line[12:].strip()
        else:
            value = line.strip()

        if not value:
            continue

        if current_section == "NAME":
            # Strip organism suffix that sometimes appears in entry NAME fields
            if " - Homo sapiens" in value:
                value = value[: value.index(" - Homo sapiens")].strip()
            parts = [p.strip() for p in value.split(" / ") if p.strip()]
            if not result["canonical_name"]:
                # First NAME line → canonical; multi-part names produce synonyms
                result["canonical_name"] = value
                if len(parts) > 1:
                    result["synonyms"].extend(parts)
            else:
                # Continuation NAME lines are additional aliases
                result["synonyms"].extend(parts)

        elif current_section == "CLASS" and not result["pathway_class"]:
            result["pathway_class"] = value

        elif current_section == "REFERENCE" and "PMID:" in value:
            raw = value.split("PMID:", 1)[1].strip().split()[0].rstrip(",;")
            if raw.isdigit():
                result["pmids"].append(raw)

    # Stable deduplication of synonyms — exclude the full canonical name
    seen: set[str] = {result["canonical_name"].lower()}
    deduped: list[str] = []
    for s in result["synonyms"]:
        if s.lower() not in seen:
            seen.add(s.lower())
            deduped.append(s)
    result["synonyms"] = deduped
    result["pmids"] = list(dict.fromkeys(result["pmids"]))

    return result


def is_metabolic(pathway_class: str) -> bool:
    return pathway_class.lower().startswith("metabolism")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(args: argparse.Namespace) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    session = build_session()

    # -- 1. Pathway list -------------------------------------------------------
    log.info("Fetching KEGG human pathway list …")
    list_text = fetch_text(
        session,
        f"{KEGG_BASE}/list/pathway/{ORGANISM}",
        CACHE_DIR / "pathway_list.txt",
    )
    all_pathways = parse_pathway_list(list_text)
    log.info("Found %d total human pathways in KEGG", len(all_pathways))

    # -- 2. Fetch & parse each entry -------------------------------------------
    records: list[dict] = []
    failed: list[str] = []

    for pathway_id, list_name in tqdm(all_pathways, desc="Fetching entries", unit="pw"):
        cache_path = CACHE_DIR / f"{pathway_id}.txt"
        try:
            entry_text = fetch_text(
                session,
                f"{KEGG_BASE}/get/{pathway_id}",
                cache_path,
            )
        except requests.HTTPError as exc:
            log.warning("HTTP error for %s: %s", pathway_id, exc)
            failed.append(pathway_id)
            continue

        parsed = parse_pathway_entry(entry_text)

        if not args.all and not is_metabolic(parsed["pathway_class"]):
            continue

        records.append(
            {
                "pathway_id": pathway_id,
                "canonical_name": parsed["canonical_name"] or list_name,
                "synonyms": parsed["synonyms"],
                "pathway_class": parsed["pathway_class"],
                "pmids": parsed["pmids"],
                "source": "kegg",
            }
        )

    # -- 3. Write output -------------------------------------------------------
    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    # -- 4. Summary stats ------------------------------------------------------
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
        log.warning("Failed pathway IDs: %s", failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch KEGG metabolic pathway data (Step 1a)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all pathway classes, not just Metabolism",
    )
    main(parser.parse_args())
