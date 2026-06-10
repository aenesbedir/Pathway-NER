#!/usr/bin/env python3
"""
fetch_pubmed.py  —  Step 1c

Fetches PubMed abstracts and PMC Open Access full-text for all PMIDs
collected in Steps 1a (KEGG) and 1b (Reactome).

Strategy:
  1. Collect + deduplicate all PMIDs from kegg_pathways.jsonl and
     reactome_pathways.jsonl.
  2. Batch-fetch PubMed records (200/request) to get title + abstract.
     Parsed results cached per-article as abs_{pmid}.json.
  3. Extract PMC IDs from PubMed XML ArticleIdList (no elink needed).
  4. Fetch PMC full-text per article; try NCBI XML first, fall back to HTML.
     Parsed result cached as pmc_{PMCID}.json.
  5. Merge and write one record per PMID.

All cache files are JSON. No XML or HTML files are persisted.

NCBI API key increases rate limit from 3 → 10 req/s.
Set via environment variable NCBI_API_KEY, or edit FALLBACK_API_KEY below.

Output : data/raw/abstracts.jsonl
Cache  : data/raw/pubmed_cache/
"""

import json
import logging
import os
import re
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
PMC_HTML_BASE = "https://pmc.ncbi.nlm.nih.gov/articles"
FALLBACK_API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
API_KEY = os.environ.get("NCBI_API_KEY", FALLBACK_API_KEY)

REQUEST_DELAY = 0.11        # ~9 req/s — stays under the 10 req/s API-key limit
BATCH_SIZE = 200            # NCBI recommended max for efetch

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
# Cache: one JSON file per article → abs_{pmid}.json
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


def _parse_pubmed_xml_batch(xml_text: str) -> dict[str, dict]:
    """Parse PubMed efetch XML → {pmid: {title, abstract, pmc_id}}."""
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

        abstract_parts = []
        for ab_el in article.findall(".//AbstractText"):
            label = ab_el.get("Label")
            text = _text_content(ab_el)
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts)

        # PMC ID is embedded in ArticleIdList — extract here to avoid a
        # separate pass over the XML later
        pmc_id = None
        for art_id in article.findall(".//ArticleIdList/ArticleId"):
            if art_id.get("IdType") == "pmc" and art_id.text:
                pmc_id = art_id.text.strip()
                break

        results[pmid] = {"title": title, "abstract": abstract, "pmc_id": pmc_id}
    return results


def fetch_pubmed_abstracts(
    session: requests.Session,
    all_pmids: list[str],
) -> dict[str, dict]:
    """
    Fetch title + abstract for all PMIDs.

    Sends batched requests (BATCH_SIZE each) and caches parsed results as
    abs_{pmid}.json per article. Already-cached articles are skipped.
    Returns {pmid: {title, abstract, pmc_id}}.
    """
    results: dict[str, dict] = {}

    # Load already-cached articles
    cached = []
    missing = []
    for pmid in all_pmids:
        cache_path = CACHE_DIR / f"abs_{pmid}.json"
        if cache_path.exists():
            results[pmid] = json.loads(cache_path.read_text(encoding="utf-8"))
            cached.append(pmid)
        else:
            missing.append(pmid)

    if cached:
        log.info("Loaded %d abstracts from cache", len(cached))

    if not missing:
        return results

    # Fetch missing PMIDs in batches
    batches = [missing[i: i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    for batch in tqdm(batches, desc="PubMed batches", unit="batch"):
        resp = get(
            session,
            f"{NCBI_BASE}/efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(batch),
                "rettype": "abstract",
                "retmode": "xml",
            },
        )
        parsed = _parse_pubmed_xml_batch(resp.text)
        for pmid, data in parsed.items():
            cache_path = CACHE_DIR / f"abs_{pmid}.json"
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            results[pmid] = data

    return results


# ---------------------------------------------------------------------------
# Step 3 — PMC full-text fetch
# Cache: pmc_{PMCID}.json → {"full_text": "..."}
# ---------------------------------------------------------------------------
def _parse_pmc_xml(xml_text: str) -> str:
    """Extract body paragraphs from PMC JATS XML → plain text."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.debug("PMC XML parse error: %s", exc)
        return ""

    body = root.find(".//body")
    if body is None:
        body = root.find(".//{http://www.ncbi.nlm.nih.gov/pmc/articles/sets/}body")
    if body is None:
        return ""

    paragraphs = []
    for p in body.findall(".//p"):
        text = _text_content(p)
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _parse_pmc_html(html: str) -> str:
    """Extract body paragraphs from PMC article HTML page."""
    match = re.search(
        r'<section[^>]*class="[^"]*body main-article-body[^"]*"[^>]*>(.*?)</section>',
        html,
        re.DOTALL,
    )
    if not match:
        return ""
    body_html = match.group(1)
    text = re.sub(r"<[^>]+>", " ", body_html)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def fetch_pmc_fulltext(session: requests.Session, pmc_id: str) -> str:
    """
    Fetch full-text for a PMCID. Returns plain text or empty string.

    Cache: pmc_{PMCID}.json with {"full_text": "..."}.
    Strategy: NCBI XML first; HTML fallback for publisher-blocked articles.
    """
    cache_path = CACHE_DIR / f"pmc_{pmc_id}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")).get("full_text", "")

    numeric_id = pmc_id.lstrip("PMCpmc")
    full_text = ""

    # -- Try XML ---------------------------------------------------------------
    try:
        resp = get(
            session,
            f"{NCBI_BASE}/efetch.fcgi",
            {"db": "pmc", "id": numeric_id, "rettype": "full", "retmode": "xml"},
        )
        full_text = _parse_pmc_xml(resp.text)
    except requests.HTTPError as exc:
        log.debug("PMC XML fetch failed for %s: %s", pmc_id, exc)

    # -- HTML fallback ---------------------------------------------------------
    if not full_text:
        try:
            resp = session.get(
                f"{PMC_HTML_BASE}/{pmc_id}/",
                headers={"User-Agent": "NER-pipeline/1.0 (research)"},
                timeout=30,
            )
            resp.raise_for_status()
            full_text = _parse_pmc_html(resp.text)
            time.sleep(REQUEST_DELAY)
        except requests.HTTPError as exc:
            log.debug("PMC HTML fetch failed for %s: %s", pmc_id, exc)

    cache_path.write_text(
        json.dumps({"full_text": full_text}, ensure_ascii=False), encoding="utf-8"
    )
    return full_text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    session = build_session()

    # -- 1. Collect PMIDs ------------------------------------------------------
    log.info("Collecting PMIDs from KEGG and Reactome outputs …")
    all_pmids = collect_pmids()
    log.info("Unique PMIDs: %d", len(all_pmids))

    # -- 2. Fetch abstracts (per-article JSON cache) ---------------------------
    log.info("Fetching PubMed abstracts …")
    pubmed_records = fetch_pubmed_abstracts(session, all_pmids)
    log.info("Abstracts fetched: %d / %d", len(pubmed_records), len(all_pmids))

    # -- 3. Identify PMIDs with PMC full-text ----------------------------------
    pmid_to_pmc: dict[str, str] = {
        pmid: data["pmc_id"]
        for pmid, data in pubmed_records.items()
        if data.get("pmc_id")
    }
    log.info("PMIDs with PMC ID: %d / %d", len(pmid_to_pmc), len(all_pmids))

    # -- 4. Fetch PMC full-text (per-article JSON cache) ----------------------
    log.info("Fetching PMC full-text for %d articles …", len(pmid_to_pmc))
    pmc_fulltext: dict[str, str] = {}
    for pmid, pmc_id in tqdm(pmid_to_pmc.items(), desc="PMC full-text", unit="article"):
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
    log.info("─" * 60)
    log.info("Output          : %s", OUTPUT_FILE)
    log.info("Total PMIDs     : %d", len(all_pmids))
    log.info("With abstract   : %d", has_abstract)
    log.info("With full-text  : %d", len(pmc_fulltext))
    log.info("Records written : %d", written)
    log.info("Skipped (empty) : %d", skipped)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
