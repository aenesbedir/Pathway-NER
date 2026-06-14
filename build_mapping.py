#!/usr/bin/env python3
"""
build_mapping.py  —  Step 1d

Produces pathway_abstract_pairs.jsonl: one record per (pathway, pmid) pair.
Article text lives in abstracts.jsonl; this file holds only the reference (pmid)
plus the pathway metadata (id, name, synonyms).

Steps:
  1. Load all pathways from kegg_pathways.jsonl + reactome_pathways.jsonl.
  2. Enrich each pathway's synonym list with matching Recon subsystem names.
  3. Join (pathway, pmid) pairs with abstracts.jsonl — skip PMIDs with no text.
  4. Write data/processed/pathway_abstract_pairs.jsonl.

KEGG and Reactome pathways are kept separate (no cross-database merging).
"""

import json
import logging
import re
from pathlib import Path

KEGG_FILE = Path("data/raw/kegg_pathways.jsonl")
REACTOME_FILE = Path("data/raw/reactome_pathways.jsonl")
ABSTRACTS_FILE = Path("data/raw/abstracts.jsonl")
RECON_FILE = Path("unique_pathways_from_recon.json")
OUTPUT_FILE = Path("data/processed/pathway_abstract_pairs.jsonl")

# Recon names that are model-internal artifacts, not real pathway names
RECON_ARTIFACTS = {
    "intracellular demand",
    "intracellular source/sink",
    "exchange/demand reaction",
    "biomass and maintenance functions",
    "miscellaneous",
    "dietary fiber binding",
    "r group synthesis",
    "protein formation",
    "drug metabolism",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for fuzzy matching."""
    text = text.lower()
    text = re.sub(r"[/,\-()]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_recon_names() -> set[str]:
    names = json.loads(RECON_FILE.read_text(encoding="utf-8"))
    return {n for n in names if n not in RECON_ARTIFACTS}


def enrich_synonyms(pathway: dict, recon_names: set[str]) -> list[str]:
    """
    Add Recon names that match the pathway's canonical name or existing synonyms.
    Match is based on normalized form equality.
    """
    existing = {normalize(s) for s in [pathway["canonical_name"]] + pathway.get("synonyms", [])}
    extra = [n for n in recon_names if normalize(n) in existing]
    combined = list(pathway.get("synonyms", []))
    for name in extra:
        if name not in combined and name != pathway["canonical_name"].lower():
            combined.append(name)
    return combined


def load_pathways() -> list[dict]:
    pathways = []
    for path in (KEGG_FILE, REACTOME_FILE):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                pathways.append(json.loads(line))
    return pathways


def load_abstracts() -> set[str]:
    """Return set of PMIDs that have at least abstract or full_text in abstracts.jsonl."""
    pmids = set()
    with ABSTRACTS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            pmids.add(record["pmid"])
    return pmids


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    recon_names = load_recon_names()
    log.info("Recon names loaded: %d (after filtering artifacts)", len(recon_names))

    pathways = load_pathways()
    log.info("Pathways loaded: %d (KEGG + Reactome)", len(pathways))

    available_pmids = load_abstracts()
    log.info("PMIDs with text in abstracts.jsonl: %d", len(available_pmids))

    written = 0
    skipped_no_pmids = 0
    skipped_no_text = 0
    recon_enriched = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for pathway in pathways:
            pmids = pathway.get("pmids", [])
            if not pmids:
                skipped_no_pmids += 1
                continue

            enriched_synonyms = enrich_synonyms(pathway, recon_names)
            if len(enriched_synonyms) > len(pathway.get("synonyms", [])):
                recon_enriched += 1

            for pmid in pmids:
                pmid = str(pmid)
                if pmid not in available_pmids:
                    skipped_no_text += 1
                    continue

                out.write(json.dumps({
                    "pathway_id": pathway["pathway_id"],
                    "source": pathway["source"],
                    "canonical_name": pathway["canonical_name"],
                    "synonyms": enriched_synonyms,
                    "pmid": pmid,
                }, ensure_ascii=False) + "\n")
                written += 1

    log.info("─" * 60)
    log.info("Output                  : %s", OUTPUT_FILE)
    log.info("Pairs written           : %d", written)
    log.info("Pathways with no PMIDs  : %d (skipped)", skipped_no_pmids)
    log.info("PMIDs with no text      : %d (skipped)", skipped_no_text)
    log.info("Pathways Recon-enriched : %d", recon_enriched)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
