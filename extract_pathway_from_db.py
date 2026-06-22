#!/usr/bin/env python3
"""
extract_pathway_from_db.py

Runs the LLM over each record in extracted_disease_pathway_db_disease_pathway_just_abstracts.json
and extracts the pathway name as it appears in the abstract text.

Input  : data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json
Output : data/processed/db_with_extracted_pathways.json  (same order, added field)
Cache  : data/raw/llm_cache_db/{pmid}__{pathway}.json  (resumable)

Run with:
    venv310/bin/python3 extract_pathway_from_db.py
"""

import json
import logging
import re
import time
from pathlib import Path

import requests
from tqdm import tqdm

from prompts.pathway_extraction import ACTIVE as PROMPT_TEMPLATE

INPUT_FILE = Path("data/raw/extracted_disease_pathway_db_disease_pathway_just_abstracts.json")
OUTPUT_FILE = Path("data/processed/db_with_extracted_pathways.json")
CACHE_DIR = Path("data/raw/llm_cache_db")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"
MAX_CHARS = 3000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def call_llm(text: str, pathway_name: str) -> list[str]:
    prompt = PROMPT_TEMPLATE.format(text=text[:MAX_CHARS], pathway_name=pathway_name)
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return []
        parsed = json.loads(json_match.group())
        return [m.strip() for m in parsed.get("matches", []) if isinstance(m, str) and m.strip()]
    except Exception as exc:
        log.debug("LLM call failed: %s", exc)
        return []


def verify(text: str, candidates: list[str]) -> list[str]:
    """Keep only candidates that exist verbatim (case-insensitive) in text."""
    text_lower = text.lower()
    return [c for c in candidates if c.lower() in text_lower]


def cache_key(pmid: str, pathway: str) -> Path:
    safe = re.sub(r'[^\w]', '_', pathway)
    return CACHE_DIR / f"{pmid}__{safe}.json"


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    records = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    log.info("Records loaded: %d", len(records))

    found = 0
    cached = 0

    for rec in tqdm(records, desc="Extracting", unit="record"):
        pmid = str(rec.get("pmid", ""))
        pathway = rec.get("pathway", "")
        abstract = (rec.get("abstract") or "").strip()

        ck = cache_key(pmid, pathway)
        if ck.exists():
            rec["extracted_pathway_names"] = json.loads(ck.read_text(encoding="utf-8"))
            if rec["extracted_pathway_names"]:
                found += 1
            cached += 1
            continue

        if not abstract:
            rec["extracted_pathway_names"] = []
            ck.write_text(json.dumps([]), encoding="utf-8")
            continue

        candidates = call_llm(abstract, pathway)
        verified = verify(abstract, candidates)
        rec["extracted_pathway_names"] = verified
        ck.write_text(json.dumps(verified, ensure_ascii=False), encoding="utf-8")

        if verified:
            found += 1

    OUTPUT_FILE.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    log.info("─" * 60)
    log.info("Output          : %s", OUTPUT_FILE)
    log.info("Total records   : %d", len(records))
    log.info("Pathway found   : %d (%.1f%%)", found, 100 * found / len(records))
    log.info("No match        : %d", len(records) - found)
    log.info("From cache      : %d", cached)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
