#!/usr/bin/env python3
"""
build_ground_truth.py

Parse the curated Excel "Pathway-Disease Relationship Example Data.xlsx"
(treated as ground truth) into a per-article evidence set, then fetch each
article's abstract + full text from NCBI.

The Excel's columns 5/6 are a per-Recon-pathway evidence bibliography: each
pathway is linked to one PMC/PubMed article. Many pathways share the same
article, so we invert it to: article -> {ground-truth pathways it is evidence for}.

Pathway names are normalized to the 98 Recon canonical names. Names that are
not Recon metabolic pathways (Transport subsystems, exchange/demand model
reactions) are kept separately as OUT-OF-SCOPE — the model was never trained to
detect them, so they must not count as misses.

Output: ground_truth_articles.json
  [ { "pmid", "pmcid", "gt_inscope": [...], "gt_outscope": [...],
      "gt_raw": [...], "abstract", "full_text" }, ... ]

Related:
  - playground/exact_match_analysis.md      (Recon pathway vocabulary)
  - playground/model_005_ground_truth_compare/compare_model.py  (next step)

Run from repo root (needs openpyxl, requests):
  /home/enes/sci-usage/venv310/bin/python3 \\
      playground/model_005_ground_truth_compare/build_ground_truth.py
"""

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl
import requests

ROOT = Path(__file__).resolve().parents[2]
XLSX = Path.home() / "Downloads" / "Pathway-Disease Relationship Example Data.xlsx"
OUT = Path(__file__).resolve().parent / "ground_truth_articles.json"

API_KEY = os.environ.get("NCBI_API_KEY", "d4e795e70597e6edfa4d1282886100ecee08")
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
EMAIL = "elifyrtkrn@gmail.com"
TOOL = "ner-pipeline"
SLEEP = 0.12

# Recon subsystem labels that are model artifacts, not literature pathway names
# (mirror of match_exact.py RECON_BLOCKLIST). These are OUT-OF-SCOPE: the model
# is designed never to detect them, so they must not count as in-scope GT.
RECON_BLOCKLIST = {
    "miscellaneous", "protein formation", "intracellular demand",
    "intracellular source/sink", "r group synthesis",
    "biomass and maintenance functions", "exchange/demand reaction",
    "dietary fiber binding",
}

# Manual overrides for names that don't normalize cleanly to a Recon canonical.
# OUT_OF_SCOPE = not one of the 98 Recon metabolic pathways.
OUT_OF_SCOPE = "__OUT_OF_SCOPE__"
OVERRIDES = {
    "androgen & estrogen synthesis/metabolism": "androgen and estrogen synthesis and metabolism",
    "cholesterol / squalene metabolism": "cholesterol metabolism",
    "exchange / demand reactions (model)": OUT_OF_SCOPE,
    "extracellular exchange": OUT_OF_SCOPE,
    "folate / one-carbon metabolism": "folate metabolism",
    "glutamate / glutamine metabolism": "glutamate metabolism",
    "glycine / serine / alanine / threonine metabolism": "glycine, serine, alanine, and threonine metabolism",
    "glycine, serine, alanine & threonine metabolism": "glycine, serine, alanine, and threonine metabolism",
    "glycolysis / gluconeogenesis": "glycolysis/gluconeogenesis",
    "inositol phosphate / phosphatidylinositol phosphate metabolism": "inositol phosphate metabolism",
    "valine / leucine / isoleucine (bcaa) metabolism": "valine, leucine, and isoleucine metabolism",
    "valine, leucine & isoleucine metabolism": "valine, leucine, and isoleucine metabolism",
}


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace("&", " and ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip(" /")
    return re.sub(r"\s+", " ", s).strip()


def map_pathway(raw: str, recon_norm: dict[str, str]) -> str | None:
    low = raw.lower().strip()
    canonical = None
    if low in OVERRIDES:
        v = OVERRIDES[low]
        canonical = None if v == OUT_OF_SCOPE else v
    else:
        key = norm(raw)
        if key in recon_norm:
            canonical = recon_norm[key]
        else:
            first = norm(raw.split("/")[0])
            canonical = recon_norm.get(first)
    # Blocklisted Recon artifacts are out of scope (model never detects them)
    if canonical in RECON_BLOCKLIST:
        return None
    return canonical


def parse_excel():
    recon = set(json.load((ROOT / "unique_pathways_from_recon.json").open()))
    recon_norm = {norm(r): r for r in recon}

    wb = openpyxl.load_workbook(XLSX, data_only=True)
    rows = list(wb["Sayfa1"].iter_rows(values_only=True))
    pat = re.compile(r"(PMC\d+)|pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")

    art_raw = defaultdict(set)
    for r in rows:
        for idx in (4, 5):
            if len(r) > idx and r[idx] and " — " in str(r[idx]):
                cell = str(r[idx]).strip()
                name = cell.split(" — ")[0].strip()
                for pmc, pm in pat.findall(cell):
                    art_raw[pmc or ("PMID:" + pm)].add(name)
    return art_raw, recon_norm


def idconv(pmcids: list[str]) -> dict[str, str]:
    """PMC id -> PMID (string). Batched."""
    out = {}
    for i in range(0, len(pmcids), 50):
        batch = pmcids[i:i + 50]
        params = {"ids": ",".join(batch), "format": "json",
                  "tool": TOOL, "email": EMAIL}
        r = requests.get(IDCONV, params=params, timeout=60)
        r.raise_for_status()
        for rec in r.json().get("records", []):
            if rec.get("pmid"):
                out[rec["requested-id"]] = str(rec["pmid"])
        time.sleep(SLEEP)
    return out


def efetch_pubmed(pmids: list[str]) -> dict[str, dict]:
    """PMID -> {abstract, title}. Batched XML."""
    out = {}
    for i in range(0, len(pmids), 100):
        batch = pmids[i:i + 100]
        params = {"db": "pubmed", "id": ",".join(batch), "retmode": "xml",
                  "api_key": API_KEY, "tool": TOOL, "email": EMAIL}
        r = requests.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=90)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//PMID")
            title = " ".join(t.strip() for t in art.itertext()
                             if False)  # placeholder; set below
            title = art.findtext(".//ArticleTitle") or ""
            abs_parts = [(a.text or "") for a in art.findall(".//Abstract/AbstractText")]
            # include label attributes' text via itertext for structured abstracts
            abs_full = " ".join("".join(a.itertext()) for a in art.findall(".//Abstract/AbstractText"))
            out[pmid] = {"title": title, "abstract": abs_full.strip()}
        time.sleep(SLEEP)
    return out


def efetch_pmc_fulltext(pmcid: str) -> str:
    numeric = pmcid.replace("PMC", "")
    params = {"db": "pmc", "id": numeric, "retmode": "xml",
              "api_key": API_KEY, "tool": TOOL, "email": EMAIL}
    try:
        r = requests.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=90)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        body = root.find(".//body")
        if body is None:
            return ""
        return " ".join(" ".join(p.itertext()) for p in body.iter("p")).strip()
    except Exception as e:
        print(f"  ! PMC fulltext failed {pmcid}: {e}")
        return ""
    finally:
        time.sleep(SLEEP)


def main():
    art_raw, recon_norm = parse_excel()
    print(f"Distinct article refs in Excel: {len(art_raw)}")

    # Resolve PMC -> PMID; PMID: refs already have pmid
    pmc_ids = [a for a in art_raw if a.startswith("PMC")]
    pmc2pmid = idconv(pmc_ids)
    print(f"Resolved {len(pmc2pmid)}/{len(pmc_ids)} PMC->PMID")

    # Merge by PMID (some PMC and PMID refs are the same article)
    merged = defaultdict(lambda: {"pmcid": None, "gt_raw": set()})
    for ref, names in art_raw.items():
        names = set(names)
        if ref.startswith("PMC"):
            pmid = pmc2pmid.get(ref)
            pmcid = ref
        else:
            pmid = ref.split(":")[1]
            pmcid = None
        if not pmid:
            print(f"  ! no PMID for {ref}; skipping")
            continue
        merged[pmid]["gt_raw"] |= names
        if pmcid:
            merged[pmid]["pmcid"] = pmcid
    print(f"Merged into {len(merged)} unique articles (by PMID)")

    # Fetch abstracts
    meta = efetch_pubmed(list(merged.keys()))

    out = []
    for pmid, info in merged.items():
        inscope, outscope = set(), set()
        for raw in info["gt_raw"]:
            m = map_pathway(raw, recon_norm)
            (inscope.add(m) if m else outscope.add(raw))
        m = meta.get(pmid, {})
        abstract = m.get("abstract", "")
        full_text = ""
        if info["pmcid"]:
            full_text = efetch_pmc_fulltext(info["pmcid"])
        out.append({
            "pmid": pmid,
            "pmcid": info["pmcid"],
            "title": m.get("title", ""),
            "gt_inscope": sorted(inscope),
            "gt_outscope": sorted(outscope),
            "gt_raw": sorted(info["gt_raw"]),
            "abstract": abstract,
            "full_text": full_text,
        })
        print(f"  {pmid} ({info['pmcid']}): gt_inscope={len(inscope)} "
              f"abs={len(abstract)}c ft={len(full_text)}c")

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(out)} articles -> {OUT}")


if __name__ == "__main__":
    main()
