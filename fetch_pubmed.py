#!/usr/bin/env python3
"""
fetch_pubmed.py  —  Step 1c

Fetches PubMed abstracts and PMC Open Access full-text for all PMIDs
collected in Steps 1a (KEGG) and 1b (Reactome).

Strategy:
  1. Collect + deduplicate all PMIDs from kegg_pathways.jsonl and
     reactome_pathways.jsonl.
  2. Batch-fetch PubMed records (200/request) to get title + abstract.
  3. Use NCBI elink to find which PMIDs have PMC Open Access full-text.
  4. Fetch PMC full-text (JATS XML) individually; extract body paragraphs.
  5. Merge and write one record per PMID.

NCBI API key increases rate limit from 3 → 10 req/s.
Set via environment variable NCBI_API_KEY, or edit FALLBACK_API_KEY below.

Output : data/raw/abstracts.jsonl
Cache  : data/raw/pubmed_cache/
"""

import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
FALLBACK_API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
API_KEY = os.environ.get("NCBI_API_KEY", FALLBACK_API_KEY)

REQUEST_DELAY = 0.11        # ~9 req/s — stays under the 10 req/s API-key limit
BATCH_SIZE = 200            # NCBI recommended max for efetch / elink

KEGG_FILE = Path("data/raw/kegg_pathways.jsonl")
REACTOME_FILE = Path("data/raw/reactome_pathways.jsonl")
OUTPUT_FILE = Path("data/raw/abstracts.jsonl")
CACHE_DIR = Path("data/raw/pubmed_cache")

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
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = "NER-pipeline/1.0 (research)"
    return session


def get(session: requests.Session, url: str, params: dict) -> requests.Response:
    params["api_key"] = API_KEY
    resp = session.get(url, params=params, timeout=60)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp


# ---------------------------------------------------------------------------
# Step 1 — collect PMIDs
# ---------------------------------------------------------------------------
def collect_pmids() -> list[str]:
    pmids: set[str] = set()
    for path in (KEGG_FILE, REACTOME_FILE):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                record = json.loads(line)
                for pmid in record.get("pmids", []):
                    if str(pmid).strip().isdigit():
                        pmids.add(str(pmid).strip())
    return sorted(pmids)


# ---------------------------------------------------------------------------
# Step 2 — PubMed batch fetch (title + abstract)
# ---------------------------------------------------------------------------
def _text_content(element: Optional[ET.Element]) -> str:
    """Concatenate all text/tail within an XML element (handles mixed content)."""
    if element is None:
        return ""
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(_text_content(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def parse_pubmed_xml(xml_text: str) -> dict[str, dict]:
    """Parse PubMed efetch XML → {pmid: {title, abstract}}."""
    results: dict[str, dict] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("XML parse error in PubMed batch: %s", exc)
        return results

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        pmid = pmid_el.text.strip()

        title_el = article.find(".//ArticleTitle")
        title = _text_content(title_el)

        # AbstractText can be a single element or multiple with Label attrs
        abstract_parts = []
        for ab_el in article.findall(".//AbstractText"):
            label = ab_el.get("Label")
            text = _text_content(ab_el)
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts)

        results[pmid] = {"title": title, "abstract": abstract}
    return results


def fetch_pubmed_batch(
    session: requests.Session,
    pmids: list[str],
    batch_index: int,
) -> dict[str, dict]:
    cache_path = CACHE_DIR / f"pubmed_batch_{batch_index:04d}.xml"
    if cache_path.exists():
        xml_text = cache_path.read_text(encoding="utf-8")
    else:
        resp = get(
            session,
            f"{NCBI_BASE}/efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(pmids),
                "rettype": "abstract",
                "retmode": "xml",
            },
        )
        xml_text = resp.text
        cache_path.write_text(xml_text, encoding="utf-8")
    return parse_pubmed_xml(xml_text)


# ---------------------------------------------------------------------------
# Step 3 — extract PMID → PMCID from already-fetched PubMed XML
# (PubMed efetch XML includes <ArticleId IdType="pmc"> — no elink call needed)
# ---------------------------------------------------------------------------
def extract_pmc_ids_from_pubmed_xml(xml_text: str) -> dict[str, str]:
    """Parse PubMed efetch XML → {pmid: pmc_id} using ArticleIdList entries."""
    pmid_to_pmc: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return pmid_to_pmc

    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        pmid = pmid_el.text.strip()
        for art_id in article.findall(".//ArticleIdList/ArticleId"):
            if art_id.get("IdType") == "pmc" and art_id.text:
                pmid_to_pmc[pmid] = art_id.text.strip()
                break

    return pmid_to_pmc


# ---------------------------------------------------------------------------
# Step 4 — PMC full-text fetch
# ---------------------------------------------------------------------------
def parse_pmc_xml(xml_text: str) -> str:
    """Extract body paragraphs from PMC JATS XML → plain text."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.debug("PMC XML parse error: %s", exc)
        return ""

    paragraphs: list[str] = []
    body = root.find(".//body")
    if body is None:
        # Some records wrap body differently
        body = root.find(".//{http://www.ncbi.nlm.nih.gov/pmc/articles/sets/}body")
    if body is None:
        return ""

    for p in body.findall(".//p"):
        text = _text_content(p)
        if text:
            paragraphs.append(text)

    return "\n\n".join(paragraphs)


def fetch_pmc_fulltext(
    session: requests.Session,
    pmc_id: str,
) -> str:
    """Fetch and parse PMC full-text for a given PMCID (e.g. 'PMC1234567')."""
    numeric_id = pmc_id.lstrip("PMCpmc")
    cache_path = CACHE_DIR / f"pmc_{pmc_id}.xml"
    if cache_path.exists():
        xml_text = cache_path.read_text(encoding="utf-8")
    else:
        try:
            resp = get(
                session,
                f"{NCBI_BASE}/efetch.fcgi",
                {
                    "db": "pmc",
                    "id": numeric_id,
                    "rettype": "full",
                    "retmode": "xml",
                },
            )
            xml_text = resp.text
            cache_path.write_text(xml_text, encoding="utf-8")
        except requests.HTTPError as exc:
            log.debug("PMC fetch failed for %s: %s", pmc_id, exc)
            return ""
    return parse_pmc_xml(xml_text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def batched(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    session = build_session()

    # -- 1. Collect PMIDs ------------------------------------------------------
    log.info("Collecting PMIDs from KEGG and Reactome outputs …")
    all_pmids = collect_pmids()
    log.info("Unique PMIDs: %d", len(all_pmids))

    # -- 2. Fetch PubMed abstracts (batched) -----------------------------------
    log.info("Fetching PubMed abstracts in batches of %d …", BATCH_SIZE)
    pubmed_records: dict[str, dict] = {}
    batches = list(batched(all_pmids, BATCH_SIZE))
    for i, batch in enumerate(tqdm(batches, desc="PubMed batches", unit="batch")):
        records = fetch_pubmed_batch(session, batch, i)
        pubmed_records.update(records)
    log.info("Abstracts fetched: %d / %d", len(pubmed_records), len(all_pmids))

    # -- 3. Extract PMC IDs from already-cached PubMed XML --------------------
    log.info("Extracting PMC IDs from PubMed XML …")
    pmid_to_pmc: dict[str, str] = {}
    for i in range(len(batches)):
        cache_path = CACHE_DIR / f"pubmed_batch_{i:04d}.xml"
        if cache_path.exists():
            xml_text = cache_path.read_text(encoding="utf-8")
            links = extract_pmc_ids_from_pubmed_xml(xml_text)
            pmid_to_pmc.update(links)

    log.info("PMIDs with PMC full-text: %d / %d", len(pmid_to_pmc), len(all_pmids))

    # -- 4. Fetch PMC full-text ------------------------------------------------
    log.info("Fetching PMC full-text for %d articles …", len(pmid_to_pmc))
    pmc_fulltext: dict[str, str] = {}
    for pmid, pmc_id in tqdm(
        pmid_to_pmc.items(), desc="PMC full-text", unit="article"
    ):
        text = fetch_pmc_fulltext(session, pmc_id)
        if text:
            pmc_fulltext[pmid] = text

    log.info("Full-text articles retrieved: %d", len(pmc_fulltext))

    # -- 5. Write output -------------------------------------------------------
    written = 0
    skipped = 0
    with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
        for pmid in all_pmids:
            pub = pubmed_records.get(pmid, {})
            abstract = pub.get("abstract", "")
            full_text = pmc_fulltext.get(pmid)
            pmc_id = pmid_to_pmc.get(pmid)

            # Skip PMIDs with neither abstract nor full-text
            if not abstract and not full_text:
                skipped += 1
                continue

            fh.write(
                json.dumps(
                    {
                        "pmid": pmid,
                        "title": pub.get("title", ""),
                        "abstract": abstract,
                        "pmc_id": pmc_id,
                        "full_text": full_text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1

    # -- 6. Summary ------------------------------------------------------------
    has_abstract = sum(1 for p in pubmed_records.values() if p.get("abstract"))
    has_fulltext = len(pmc_fulltext)

    log.info("─" * 60)
    log.info("Output          : %s", OUTPUT_FILE)
    log.info("Total PMIDs     : %d", len(all_pmids))
    log.info("With abstract   : %d", has_abstract)
    log.info("With full-text  : %d", has_fulltext)
    log.info("Records written : %d", written)
    log.info("Skipped (empty) : %d", skipped)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
