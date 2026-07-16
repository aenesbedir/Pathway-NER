#!/usr/bin/env python3
"""
run_silver.py

Phase 3 / Faz 1c — produce variation-aware **silver** span labels over a sample of
abstracts using the config chosen in Faz 0 (P3-0c/d):
    qwen2.5:14b, no-vocab + lenient + synonyms, plus the deterministic booster.

Flow per abstract (one LLM call):
    extract_guided() + boost()  ->  merge()  ->  canonicalize()  ->  spans

Silver is machine-labeled and noisy — it goes to doccano for human review before it
is trusted for training. It is kept strictly apart from the gold set
(playground/golden_set/).

**The 5 golden PMIDs are excluded from the sample.** They are all present in the
candidate pool; since silver becomes training data, including them would mean
training on our own eval set.

Input  : data/processed/exact_matches.jsonl  (pmid -> query pathways)
         data/raw/articles.json              (abstracts)
         data/raw/pathway_disease_pairs.json (disease category, for stratification)
Output : data/silver/pilot_1k.jsonl
Cache  : data/raw/llm_cache_silver/{pmid}.json  (resumable — the full run is ~2h)

Run from repo root:
    venv310/bin/python3 llm/run_silver.py --limit 20      # throughput check
    venv310/bin/python3 llm/run_silver.py                 # full 1k pilot
"""

import argparse
import json
import logging
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm"))

from booster import boost, merge  # noqa: E402
from canonicalize import canonicalize, match_type_for  # noqa: E402
from extract_guided import extract_guided  # noqa: E402

MATCHES_FILE = ROOT / "data/processed/exact_matches.jsonl"
ARTICLES_FILE = ROOT / "data/raw/articles.json"
PAIRS_FILE = ROOT / "data/raw/pathway_disease_pairs.json"
OUTPUT_FILE = ROOT / "data/silver/pilot_1k.jsonl"
CACHE_DIR = ROOT / "data/raw/llm_cache_silver"

MODEL = "qwen2.5:14b"

# Golden-set PMIDs — excluded so silver never trains on the eval set.
GOLDEN_PMIDS = {"11469814", "29615816", "36294866", "39934780", "40225847"}

# Heuristic for the known booster artifact: a partial span picked out of a longer
# enumeration ("proline metabolism" inside "Arginine and proline metabolism").
_LIST_CONTINUATION = re.compile(r"(?:\band\b|,)\s*$", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def load_query_pathways() -> dict[str, list[str]]:
    by_pmid: dict[str, set[str]] = defaultdict(set)
    with MATCHES_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                by_pmid[str(r["pmid"])].add(r["pathway_id"])
    return {k: sorted(v) for k, v in by_pmid.items()}


def load_categories() -> dict[str, str]:
    """pmid -> primary disease category (deterministic when a pmid has several)."""
    cats: dict[str, set[str]] = defaultdict(set)
    for rec in json.loads(PAIRS_FILE.read_text(encoding="utf-8")):
        for pmid in rec.get("pmids", []):
            cats[str(pmid)].add(rec["disease_category"])
    return {p: sorted(c)[0] for p, c in cats.items()}


def load_abstracts() -> dict[str, str]:
    arts = json.loads(ARTICLES_FILE.read_text(encoding="utf-8"))
    return {str(a["pmid"]): (a.get("abstract") or "").strip() for a in arts}


def select_sample(n: int, seed: int, qmap, abstracts, cats) -> list[str]:
    """Stratified by disease category, proportional to the pool, fixed seed."""
    pool = [p for p in qmap
            if p not in GOLDEN_PMIDS and len(abstracts.get(p, "")) > 100]
    by_cat: dict[str, list[str]] = defaultdict(list)
    for p in pool:
        by_cat[cats.get(p, "unknown")].append(p)

    rng = random.Random(seed)
    sample: list[str] = []
    for cat in sorted(by_cat):
        members = sorted(by_cat[cat])
        rng.shuffle(members)
        take = round(n * len(members) / len(pool))
        sample.extend(members[:take])
    rng.shuffle(sample)
    return sample[:n]


def process_one(pmid: str, text: str, qps: list[str], model: str) -> dict:
    cache = CACHE_DIR / f"{pmid}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    llm_spans = extract_guided(text, qps, model=model)
    merged = merge(llm_spans, boost(text))

    spans = []
    for s in merged:
        if s.get("source") == "booster":
            canonical = s["canonical"]
            mtype = match_type_for(s["surface"], canonical)
            source = "booster"
        else:
            canonical, mtype = canonicalize(s["surface"])
            source = "llm_silver"
        before = text[max(0, s["start"] - 8):s["start"]]
        spans.append({
            "start": s["start"], "end": s["end"], "text": s["surface"],
            "canonical": canonical, "match_type": mtype, "source": source,
            "maybe_partial": bool(source == "booster" and _LIST_CONTINUATION.search(before)),
        })

    rec = {"pmid": pmid, "model": model, "query_pathways": qps, "spans": spans}
    cache.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="sample size")
    ap.add_argument("--limit", type=int, default=None,
                    help="process only the first N of the sample (throughput check)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--output", default=str(OUTPUT_FILE))
    args = ap.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    qmap = load_query_pathways()
    abstracts = load_abstracts()
    cats = load_categories()
    sample = select_sample(args.n, args.seed, qmap, abstracts, cats)
    if args.limit:
        sample = sample[:args.limit]

    log.info("Sample: %d pmids (golden excluded) | model=%s", len(sample), args.model)

    records, cached = [], 0
    t0 = time.time()
    for pmid in tqdm(sample, desc="Silver", unit="abstract"):
        was_cached = (CACHE_DIR / f"{pmid}.json").exists()
        records.append(process_one(pmid, abstracts[pmid], qmap[pmid], args.model))
        cached += was_cached

    elapsed = time.time() - t0
    with Path(args.output).open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- stats ----------------------------------------------------------------
    spans = [s for r in records for s in r["spans"]]
    src = Counter(s["source"] for s in spans)
    mt = Counter(s["match_type"] for s in spans)
    unmapped = sum(1 for s in spans if s["canonical"] is None)
    partial = sum(1 for s in spans if s["maybe_partial"])
    fresh = len(sample) - cached

    log.info("─" * 60)
    log.info("Output           : %s", args.output)
    log.info("Abstracts        : %d  (fresh %d, cached %d)", len(sample), fresh, cached)
    if fresh:
        log.info("Throughput       : %.1fs/abstract  -> 1k ≈ %.1f h",
                 elapsed / fresh, elapsed / fresh * 1000 / 3600)
    log.info("Spans            : %d  (%.1f per abstract)", len(spans),
             len(spans) / max(1, len(sample)))
    log.info("  by source      : %s", dict(src))
    log.info("  by match_type  : %s", dict(mt))
    log.info("  unmapped       : %d (%.0f%%)  [golden baseline 16%%]",
             unmapped, 100 * unmapped / max(1, len(spans)))
    log.info("  maybe_partial  : %d (%.0f%%)  [booster artifact watch]",
             partial, 100 * partial / max(1, len(spans)))
    log.info("─" * 60)


if __name__ == "__main__":
    main()
