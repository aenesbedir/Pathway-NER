#!/usr/bin/env python3
"""
match_llm.py  —  Step 3

For (pathway, pmid) pairs that Step 2 found no spans for, asks a local LLM
(via Ollama) whether the text mentions the pathway by any name or abbreviation.

Every LLM-returned string is verified to exist verbatim in the source text
before being accepted as a span. Hallucinated strings are silently dropped.

Reads  : data/processed/exact_matches.jsonl   (Step 2 output)
         data/processed/pathway_abstract_pairs.jsonl
         data/raw/abstracts.jsonl
Writes : data/processed/all_matches.jsonl     (exact + LLM spans, all 1366 pairs)
Cache  : data/raw/llm_cache/{pathway_id}__{pmid}.json  (resumable)

Run with:
    venv310/bin/python3 llm/match_llm.py
"""

import json
import logging
import re
import time
from pathlib import Path

import requests
from tqdm import tqdm

from prompts.pathway_extraction import ACTIVE as PROMPT_TEMPLATE

EXACT_FILE = Path("data/processed/exact_matches.jsonl")
PAIRS_FILE = Path("data/processed/pathway_abstract_pairs.jsonl")
ABSTRACTS_FILE = Path("data/raw/abstracts.jsonl")
OUTPUT_FILE = Path("data/processed/all_matches.jsonl")
CACHE_DIR = Path("data/raw/llm_cache")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

# Max characters to send to LLM (abstract preferred; fall back to full_text[:MAX_CHARS])
MAX_CHARS = 3000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_exact_matches() -> dict[tuple, dict]:
    records = {}
    with EXACT_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            records[(r["pathway_id"], r["pmid"])] = r
    return records


def load_pairs() -> dict[tuple, dict]:
    pairs = {}
    with PAIRS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            pairs[(r["pathway_id"], r["pmid"])] = r
    return pairs


def load_abstracts() -> dict[str, dict]:
    abstracts = {}
    with ABSTRACTS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            abstracts[r["pmid"]] = r
    return abstracts


# ---------------------------------------------------------------------------
# Text selection
# ---------------------------------------------------------------------------

def get_text(article: dict) -> tuple[str, str]:
    """Return (text, source) — abstract preferred, full_text[:MAX_CHARS] as fallback."""
    abstract = (article.get("abstract") or "").strip()
    if abstract:
        return abstract[:MAX_CHARS], "abstract"
    full_text = (article.get("full_text") or "").strip()
    if full_text:
        return full_text[:MAX_CHARS], "full_text"
    return "", ""


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(text: str, pathway_name: str) -> list[str]:
    prompt = PROMPT_TEMPLATE.format(text=text, pathway_name=pathway_name)
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        # Extract JSON even if LLM wraps it in markdown code fences
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            return []
        parsed = json.loads(json_match.group())
        matches = parsed.get("matches", [])
        return [m for m in matches if isinstance(m, str) and m.strip()]
    except Exception as exc:
        log.debug("LLM call failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Span verification
# ---------------------------------------------------------------------------

def verify_spans(text: str, source: str, candidates: list[str]) -> list[dict]:
    """Return only candidates that exist verbatim (case-insensitive) in text."""
    spans = []
    text_lower = text.lower()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        pos = text_lower.find(candidate.lower())
        if pos == -1:
            log.debug("LLM hallucination dropped: %r", candidate)
            continue
        spans.append({
            "start": pos,
            "end": pos + len(candidate),
            "text": text[pos: pos + len(candidate)],
            "source": source,
        })
    return spans


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def cache_path(pathway_id: str, pmid: str) -> Path:
    safe_id = pathway_id.replace("/", "_")
    return CACHE_DIR / f"{safe_id}__{pmid}.json"


def load_cache(pathway_id: str, pmid: str) -> list[dict] | None:
    p = cache_path(pathway_id, pmid)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def save_cache(pathway_id: str, pmid: str, spans: list[dict]) -> None:
    p = cache_path(pathway_id, pmid)
    p.write_text(json.dumps(spans, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading data …")
    exact_matches = load_exact_matches()
    pairs = load_pairs()
    abstracts = load_abstracts()

    unmatched = [(k, v) for k, v in exact_matches.items() if not v["spans"]]
    log.info("Pairs to process via LLM: %d / %d", len(unmatched), len(exact_matches))

    llm_found = 0
    llm_hallucinations = 0
    cached_hits = 0

    for (pathway_id, pmid), record in tqdm(unmatched, desc="LLM matching", unit="pair"):
        pair = pairs[(pathway_id, pmid)]
        article = abstracts.get(pmid, {})
        text, source = get_text(article)
        if not text:
            continue

        # Check cache first
        cached = load_cache(pathway_id, pmid)
        if cached is not None:
            exact_matches[(pathway_id, pmid)]["spans"] = cached
            if cached:
                llm_found += 1
                cached_hits += 1
            continue

        candidates = call_llm(text, pair["canonical_name"])
        llm_hallucinations += len(candidates)

        spans = verify_spans(text, source, candidates)
        llm_hallucinations -= len(spans)  # subtract verified ones

        save_cache(pathway_id, pmid, spans)
        exact_matches[(pathway_id, pmid)]["spans"] = spans

        if spans:
            llm_found += 1

    # Write merged output (all 1366 pairs)
    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for record in exact_matches.values():
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    total = len(exact_matches)
    with_spans = sum(1 for r in exact_matches.values() if r["spans"])
    total_spans = sum(len(r["spans"]) for r in exact_matches.values())

    log.info("─" * 60)
    log.info("Output              : %s", OUTPUT_FILE)
    log.info("Total pairs         : %d", total)
    log.info("With spans (total)  : %d (%.1f%%)", with_spans, 100 * with_spans / total)
    log.info("  — from Step 2     : %d", with_spans - llm_found)
    log.info("  — from LLM        : %d", llm_found)
    log.info("  — from cache      : %d", cached_hits)
    log.info("Hallucinations drop : %d", llm_hallucinations)
    log.info("No spans (Step 5)   : %d", total - with_spans)
    log.info("Total spans         : %d", total_spans)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
