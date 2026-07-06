#!/usr/bin/env python3
"""
fetch_articles.py

Fetches full text (via PMC) or abstract (via PubMed) for every PMID
in pathway_disease_pairs.json, along with metadata.

Flow per PMID:
  1. ELink pubmed → pmc  →  PMCID           (cached per PMID)
  2a. PMCID found  → EFetch PMC JATS XML → full text + abstract + sections
  2b. No PMCID     → EFetch PubMed abstract XML
  Both paths also pull metadata from PubMed XML (MeSH, pub type, year, DOI, etc.)

Output:
  data/raw/articles.json   — JSON array, one object per article:
  {
    "pmid":          "12345678",
    "pmcid":         "PMC1234567",
    "doi":           "10.1016/...",
    "title":         "...",
    "year":          2021,
    "journal":       "Nature Metabolism",
    "pub_types":     ["Journal Article", "Research Support, N.I.H., Extramural"],
    "keywords":      ["oxidative phosphorylation", "neurodegeneration"],
    "mesh_headings": [
      {"term": "Alzheimer Disease", "ui": "D000544", "major": true,  "qualifiers": ["metabolism"]},
      {"term": "Mitochondria",      "ui": "D008928", "major": false, "qualifiers": ["physiology"]}
    ],
    "abstract":      "...",
    "sections": [                          -- empty list if no full text
      {"label": "Introduction", "text": "..."},
      {"label": "Results",      "text": "..."}
    ],
    "full_text":     "...",                -- concatenated section texts; "" if abstract only
    "has_full_text": true
  }

Linkage:
  pathway_disease_pairs.json  →  pmids[]  →  articles.json (join on pmid)

Run:
  cd /home/enes/NER-pipeline
  python3 pubmed_api/fetch_articles.py [--pairs data/raw/pathway_disease_pairs.json]
"""

import argparse
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

FALLBACK_API_KEY = "d4e795e70597e6edfa4d1282886100ecee08"
API_KEY = os.environ.get("NCBI_API_KEY", FALLBACK_API_KEY)
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

OUTPUT = Path("data/raw/articles.json")
CACHE_DIR = Path("data/raw/article_cache")
SLEEP = 0.11
PUBMED_BATCH = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── ELink: PMID → PMCID (batch) ────────────────────────────────────────────

ELINK_BATCH = 25

def elink_batch_pubmed_to_pmc(pmids: list[str]) -> dict[str, str | None]:
    """Batch ELink via POST: returns {pmid: pmcid_or_None} for all pmids."""
    results: dict[str, str | None] = {}
    to_fetch: list[str] = []

    for pmid in pmids:
        cache_file = CACHE_DIR / f"elink_{pmid}.json"
        if cache_file.exists():
            results[pmid] = json.loads(cache_file.read_text())
        else:
            to_fetch.append(pmid)

    for i in range(0, len(to_fetch), ELINK_BATCH):
        batch = to_fetch[i : i + ELINK_BATCH]
        post_data = f"dbfrom=pubmed&db=pmc&linkname=pubmed_pmc&retmode=json&api_key={API_KEY}&" + "&".join(f"id={p}" for p in batch)
        try:
            resp = requests.post(
                f"{BASE_URL}/elink.fcgi",
                data=post_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            # Each linkset corresponds to one source PMID
            pmcid_map: dict[str, str | None] = {}
            for linkset in data.get("linksets", []):
                src_ids = [str(x) for x in linkset.get("ids", [])]
                if src_ids:
                    src_pmid = src_ids[0]
                    pmcid = None
                    for lsdb in linkset.get("linksetdbs", []):
                        if lsdb.get("dbto") == "pmc":
                            links = lsdb.get("links", [])
                            if links:
                                pmcid = str(links[0])
                                break
                    pmcid_map[src_pmid] = pmcid
            for pmid in batch:
                pmcid = pmcid_map.get(pmid)
                (CACHE_DIR / f"elink_{pmid}.json").write_text(json.dumps(pmcid))
                results[pmid] = pmcid
            time.sleep(SLEEP)
        except Exception as e:
            log.warning("ELink batch failed (offset %d, size %d): %s", i, len(batch), e)
            # On batch failure, retry each PMID individually
            for pmid in batch:
                cache_file = CACHE_DIR / f"elink_{pmid}.json"
                if cache_file.exists():
                    results[pmid] = json.loads(cache_file.read_text())
                    continue
                try:
                    r = requests.get(
                        f"{BASE_URL}/elink.fcgi",
                        params={"dbfrom": "pubmed", "db": "pmc", "id": pmid,
                                "retmode": "json", "api_key": API_KEY},
                        timeout=8,
                    )
                    r.raise_for_status()
                    d = r.json()
                    pmcid = None
                    for ls in d.get("linksets", []):
                        for lsdb in ls.get("linksetdbs", []):
                            if lsdb.get("dbto") == "pmc":
                                links = lsdb.get("links", [])
                                if links:
                                    pmcid = str(links[0])
                                    break
                    cache_file.write_text(json.dumps(pmcid))
                    results[pmid] = pmcid
                    time.sleep(SLEEP)
                except Exception as e2:
                    log.warning("ELink single failed for PMID %s: %s", pmid, e2)
                    cache_file.write_text(json.dumps(None))
                    results[pmid] = None

    return results


# ─── PubMed metadata (MeSH, pub type, year, DOI, keywords, journal) ─────────

def fetch_pubmed_batch(pmids: list[str]) -> dict[str, dict]:
    """Batch-fetch PubMed XML records. Returns {pmid: metadata_dict}."""
    results: dict[str, dict] = {}
    to_fetch: list[str] = []

    for pmid in pmids:
        cache_file = CACHE_DIR / f"pubmed_{pmid}.json"
        if cache_file.exists():
            results[pmid] = json.loads(cache_file.read_text(encoding="utf-8"))
        else:
            to_fetch.append(pmid)

    for i in range(0, len(to_fetch), PUBMED_BATCH):
        batch = to_fetch[i : i + PUBMED_BATCH]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml",
            "api_key": API_KEY,
        }
        try:
            resp = requests.get(f"{BASE_URL}/efetch.fcgi", params=params, timeout=60)
            resp.raise_for_status()
            parsed = _parse_pubmed_xml(resp.text)
            for rec in parsed:
                pmid = rec["pmid"]
                results[pmid] = rec
                (CACHE_DIR / f"pubmed_{pmid}.json").write_text(
                    json.dumps(rec, ensure_ascii=False), encoding="utf-8"
                )
            log.info(
                "  PubMed batch %d–%d: %d records",
                i + 1, min(i + PUBMED_BATCH, len(to_fetch)), len(parsed),
            )
            time.sleep(SLEEP)
        except Exception as e:
            log.warning("PubMed batch EFetch failed (offset %d): %s", i, e)

    return results


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse PubMed EFetch XML into structured metadata dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    records = []
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None else ""
        if not pmid:
            continue

        # Title
        title_el = article.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""

        # Abstract
        parts = []
        for ab in article.findall(".//AbstractText"):
            text = "".join(ab.itertext()).strip()
            if text:
                label = ab.get("Label", "")
                parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(parts)

        # Year
        year = None
        for date_el in article.findall(".//PubDate"):
            y = date_el.find("Year")
            if y is not None and y.text:
                try:
                    year = int(y.text.strip())
                except ValueError:
                    pass
                break

        # Journal
        journal_el = article.find(".//Journal/Title")
        journal = journal_el.text.strip() if journal_el is not None else ""

        # DOI
        doi = ""
        for aid in article.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text.strip() if aid.text else ""
                break

        # Publication types
        pub_types = [
            pt.text.strip()
            for pt in article.findall(".//PublicationType")
            if pt.text
        ]

        # Author keywords
        keywords = [
            kw.text.strip()
            for kw in article.findall(".//Keyword")
            if kw.text
        ]

        # MeSH headings
        mesh_headings = []
        for mh in article.findall(".//MeshHeading"):
            desc = mh.find("DescriptorName")
            if desc is None:
                continue
            qualifiers = [
                q.text.strip()
                for q in mh.findall("QualifierName")
                if q.text
            ]
            mesh_headings.append({
                "term": desc.text.strip() if desc.text else "",
                "ui": desc.get("UI", ""),
                "major": desc.get("MajorTopicYN", "N") == "Y",
                "qualifiers": qualifiers,
            })

        records.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "year": year,
            "journal": journal,
            "doi": doi,
            "pub_types": pub_types,
            "keywords": keywords,
            "mesh_headings": mesh_headings,
        })

    return records


# ─── PMC full text ───────────────────────────────────────────────────────────

def fetch_pmc_xml(pmcid: str) -> str | None:
    cache_file = CACHE_DIR / f"pmc_{pmcid}.xml"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    params = {
        "db": "pmc",
        "id": pmcid,
        "rettype": "xml",
        "retmode": "xml",
        "api_key": API_KEY,
    }
    try:
        resp = requests.get(f"{BASE_URL}/efetch.fcgi", params=params, timeout=60)
        resp.raise_for_status()
        xml_text = resp.text
        cache_file.write_text(xml_text, encoding="utf-8")
        time.sleep(SLEEP)
        return xml_text
    except Exception as e:
        log.warning("PMC EFetch failed for PMCID %s: %s", pmcid, e)
        return None


def parse_pmc_xml(xml_text: str) -> dict | None:
    """
    Parse JATS XML (PMC EFetch).
    Returns {title, abstract, sections, full_text}.
    sections = [{"label": str, "text": str}, ...]
    """
    xml_text = xml_text.replace(' xmlns="', ' _xmlns="')
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.warning("PMC XML parse error: %s", e)
        return None

    # Title
    title_el = root.find(".//article-title")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""

    # Abstract (may be structured)
    abstract_parts = []
    for ab in root.findall(".//abstract"):
        text = " ".join(t.strip() for t in "".join(ab.itertext()).split("\n") if t.strip())
        if text:
            abstract_parts.append(text)
    abstract = " ".join(abstract_parts)

    # Body sections — preserve section labels
    sections = []
    body = root.find(".//body")
    if body is not None:
        for sec in body.findall(".//sec"):
            label_el = sec.find("title")
            label = "".join(label_el.itertext()).strip() if label_el is not None else ""
            # Collect paragraphs directly in this section (not nested sub-sections)
            paras = []
            for child in sec:
                if child.tag == "p":
                    text = "".join(child.itertext()).strip()
                    if text:
                        paras.append(text)
            if paras:
                sections.append({"label": label, "text": " ".join(paras)})

        # Fallback: if no <sec> found, grab all <p> from body
        if not sections:
            paras = [
                "".join(p.itertext()).strip()
                for p in body.findall(".//p")
                if "".join(p.itertext()).strip()
            ]
            if paras:
                sections.append({"label": "", "text": " ".join(paras)})

    full_text = " ".join(s["text"] for s in sections)
    return {"title": title, "abstract": abstract, "sections": sections, "full_text": full_text}


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pairs",
        default="data/raw/pathway_disease_pairs.json",
        help="Path to pathway_disease_pairs.json",
    )
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    all_pmids = sorted({pmid for pair in pairs for pmid in pair["pmids"]})
    log.info("Pairs: %d  |  Unique PMIDs: %d", len(pairs), len(all_pmids))

    # Step 1: ELink all PMIDs → PMCIDs (batch mode)
    log.info("Step 1/3: ELink PMID → PMCID (batch=%d)...", ELINK_BATCH)
    pmid_to_pmcid = elink_batch_pubmed_to_pmc(all_pmids)
    n_pmc = sum(1 for v in pmid_to_pmcid.values() if v)
    log.info("  ELink done: %d / %d → PMC", n_pmc, len(all_pmids))

    pmc_pmids = [p for p in all_pmids if pmid_to_pmcid[p]]
    log.info("PMC full text: %d  |  Abstract only: %d", len(pmc_pmids), len(all_pmids) - len(pmc_pmids))

    # Step 2: Fetch PubMed metadata for ALL PMIDs (MeSH, year, DOI, etc.)
    log.info("Step 2/3: Fetching PubMed metadata for all %d articles...", len(all_pmids))
    pubmed_data = fetch_pubmed_batch(all_pmids)

    # Step 3: Fetch PMC full texts
    log.info("Step 3/3: Fetching PMC full texts for %d articles...", len(pmc_pmids))
    pmc_data: dict[str, dict] = {}
    for i, pmid in enumerate(pmc_pmids):
        pmcid = pmid_to_pmcid[pmid]
        xml_text = fetch_pmc_xml(pmcid)
        if xml_text:
            parsed = parse_pmc_xml(xml_text)
            if parsed:
                pmc_data[pmid] = {"pmcid": f"PMC{pmcid}", **parsed}
        if (i + 1) % 100 == 0 or (i + 1) == len(pmc_pmids):
            log.info("  PMC %d / %d", i + 1, len(pmc_pmids))

    # Assemble final records
    log.info("Assembling output...")
    articles = []
    for pmid in all_pmids:
        meta = pubmed_data.get(pmid, {})
        pmc = pmc_data.get(pmid)

        rec = {
            "pmid": pmid,
            "pmcid": pmc.get("pmcid", "") if pmc else "",
            "doi": meta.get("doi", ""),
            "title": meta.get("title") or (pmc.get("title", "") if pmc else ""),
            "year": meta.get("year"),
            "journal": meta.get("journal", ""),
            "pub_types": meta.get("pub_types", []),
            "keywords": meta.get("keywords", []),
            "mesh_headings": meta.get("mesh_headings", []),
            "abstract": meta.get("abstract") or (pmc.get("abstract", "") if pmc else ""),
            "sections": pmc.get("sections", []) if pmc else [],
            "full_text": pmc.get("full_text", "") if pmc else "",
            "has_full_text": bool(pmc and pmc.get("full_text")),
        }
        articles.append(rec)

    OUTPUT.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")

    has_full = sum(1 for a in articles if a["has_full_text"])
    log.info("Done. Articles written: %d", len(articles))
    log.info("  Has full text : %d / %d (%.1f%%)", has_full, len(articles), 100 * has_full / len(articles) if articles else 0)
    log.info("  Abstract only : %d / %d", len(articles) - has_full, len(articles))
    log.info("  Saved → %s", OUTPUT)


if __name__ == "__main__":
    main()
