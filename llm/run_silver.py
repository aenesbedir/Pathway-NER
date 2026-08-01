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

**The 10 golden PMIDs (v1: 5, v2: +5) are excluded from the sample.** Since silver
becomes training data, including any gold PMID would mean training on our own eval set.

Input  : data/processed/exact_matches.jsonl  (pmid -> query pathways)
         data/raw/articles.json              (abstracts)
         data/raw/pathway_disease_pairs.json (disease category, for stratification)
Output : data/silver/pilot_1k.jsonl
         plus <output stem>_pmids.txt — the effective sample, in output order, ready
         to feed back as --pmids. Written every run except --limit (a partial head of
         the sample) and --no-freeze.
Cache  : data/raw/llm_cache_silver/{model}/{pmid}.json  (resumable — a 1k run is ~2h)
         Scoped per model on purpose: keyed on pmid alone, swapping the model replayed
         the previous model's answers for every abstract already seen, so a re-label
         run looked successful and changed nothing. Config per model lives in
         llm/models.py.
         A failed LLM call is never cached: its empty result is indistinguishable
         from "no pathway mentioned" and the cache is the resume key, so caching it
         would lose the abstract for good. Such pmids are dropped from the output
         and reported — re-run to retry just them.

Sample selection is either **frozen** (--pmids: run exactly the pmids in the given
file(s)) or **sampled** (--number-of-articles, stratified by disease category, minus
--exclude files and always minus GOLDEN_PMIDS). The two are mutually exclusive.

Freezing exists because the sampler is not stable across vocabulary changes: widening
GOLDEN_PMIDS from 5 to 10 re-proportioned every category and re-walked the RNG, shifting
the 1k draw by 49% even at the same seed. data/silver/pilot_1k_pmids.txt pins the sample
the doccano batches were built from, so a model swap re-labels *those* abstracts rather
than a different thousand.

Run from repo root:
    venv310/bin/python3 llm/run_silver.py --limit 20            # throughput check
    venv310/bin/python3 llm/run_silver.py                       # sample a fresh 1k

    # reproduce the doccano pilot exactly (e.g. to re-label it with another model)
    venv310/bin/python3 llm/run_silver.py \\
        --pmids data/silver/pilot_1k_pmids.txt

    # 2000 new abstracts, touching neither the golden set nor the pilot
    venv310/bin/python3 llm/run_silver.py --number-of-articles 2000 \\
        --exclude playground/golden_set/golden_pmids.txt \\
                  data/silver/pilot_1k_pmids.txt
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
from typing import Optional

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "llm"))

from booster import boost, merge  # noqa: E402
from canonicalize import canonicalize, match_type_for  # noqa: E402
from extract_guided import LLMCallError, extract_guided  # noqa: E402
from models import DEFAULT, ModelSpec, resolve  # noqa: E402

MATCHES_FILE = ROOT / "data/processed/exact_matches.jsonl"
ARTICLES_FILE = ROOT / "data/raw/articles.json"
PAIRS_FILE = ROOT / "data/raw/pathway_disease_pairs.json"
OUTPUT_FILE = ROOT / "data/silver/pilot_1k.jsonl"
CACHE_ROOT = ROOT / "data/raw/llm_cache_silver"

MODEL = DEFAULT

# Golden-set PMIDs — excluded so silver never trains on the eval set.
# Keep in sync with playground/golden_set/build_golden_set.py (PMIDS_V1 + PMIDS_V2).
GOLDEN_PMIDS = {
    # v1
    "11469814", "29615816", "36294866", "39934780", "40225847",
    # v2
    "34376485", "42299101", "28587170", "38669820", "37807318",
}

# NOTE: an earlier version carried a `maybe_partial` flag for booster spans clipped out
# of an enumeration (`proline metabolism` inside `Arginine and proline metabolism`).
# Measured on the 1k pilot: **zero** such spans exist — merge() already resolves them,
# because the LLM reliably returns the full canonical name and the longer span wins.
# The flag fired on 23 correct spans instead (normal list items like `gluconeogenesis`
# in "glycolysis, gluconeogenesis, and ..."), so it was removed rather than mislead
# annotators into "fixing" good boundaries.

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def load_query_pathways() -> dict[str, list[str]]:
    """pmid -> query pathway names.

    `exact_matches.jsonl` carries `pathway_id: null` rows (pairs Step 2 found no span
    for), which must not leak into the prompt hints or the export metadata.
    """
    by_pmid: dict[str, set[str]] = defaultdict(set)
    with MATCHES_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                if r.get("pathway_id"):
                    by_pmid[str(r["pmid"])].add(r["pathway_id"])
                else:
                    by_pmid.setdefault(str(r["pmid"]), set())
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


def load_pmid_file(path: str) -> list[str]:
    """PMIDs from a one-per-line text file; `#` comments and blank lines ignored."""
    out: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        pmid = line.split("#", 1)[0].strip()
        if pmid:
            out.append(pmid)
    return out


def load_pmid_files(paths: list[str]) -> list[str]:
    """Union of several pmid files, de-duplicated, first-seen order preserved.

    Order matters for --pmids: keeping the file's order makes a re-run of a frozen
    sample line-comparable with the output it was frozen from.
    """
    out, seen = [], set()
    for path in paths:
        for pmid in load_pmid_file(path):
            if pmid not in seen:
                seen.add(pmid)
                out.append(pmid)
    return out


def select_sample(n: int, seed: int, qmap, abstracts, cats,
                  exclude: set[str] = frozenset()) -> list[str]:
    """Stratified by disease category, proportional to the pool, fixed seed.

    `exclude` is dropped from the pool on top of GOLDEN_PMIDS (which is never
    sampleable). Note the draw is only reproducible for a *fixed* pool: changing
    what is excluded re-proportions every category and re-walks the RNG, so the
    sample shifts wholesale. Freeze a sample to a file and pass it back via
    --pmids when it has to survive that.
    """
    blocked = GOLDEN_PMIDS | set(exclude)
    pool = [p for p in qmap
            if p not in blocked and len(abstracts.get(p, "")) > 100]
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


def _annotate(spans: list[dict], text: str, pmid: str, model: str, qps: list[str]) -> dict:
    """Derive canonical/match_type from raw (surface, offset, source) spans.

    Cheap and deterministic — kept separate from the LLM call so that a canonicalizer
    change can be re-applied over the cache without paying for inference again
    (see --recanonicalize).
    """
    out = []
    for s in spans:
        if s.get("source") == "booster":
            canonical = s["canonical"]          # the booster knows what it searched for
            mtype = match_type_for(s["surface"], canonical)
            source = "booster"
        else:
            canonical, mtype = canonicalize(s["surface"])
            source = "llm_silver"
        out.append({
            "start": s["start"], "end": s["end"], "text": s["surface"],
            "canonical": canonical, "match_type": mtype, "source": source,
        })
    return {"pmid": pmid, "model": model, "query_pathways": qps, "spans": out}


def _rebuild_from_cached(rec: dict, text: str) -> list[dict]:
    """Rebuild raw spans from cache without an LLM call.

    Only the LLM spans are recovered from cache — the booster is re-run from scratch
    (pure regex, free) because its own canonical assignment is baked into the cached
    record and must not survive a booster change. merge() is re-applied too.
    """
    llm_spans = [{"surface": s["text"], "start": s["start"], "end": s["end"]}
                 for s in rec["spans"] if s["source"] == "llm_silver"]
    return merge(llm_spans, boost(text))


def cache_dir_for(spec: ModelSpec) -> Path:
    return CACHE_ROOT / spec.cache_slug


def freeze_pmids(records: list[dict], output: Path, spec: ModelSpec, seed: int,
                 sampled: bool) -> Path:
    """Write the effective sample to `<output stem>_pmids.txt`, in output order.

    "Effective" is the point: it lists the pmids that actually produced a record, so
    golden leaks, pmids with no abstract and failed LLM calls are already gone. Feed
    it back with --pmids to reproduce this exact run.

    Written on every run rather than behind a flag — the stratified sampler is not
    stable across vocabulary changes (widening GOLDEN_PMIDS v1->v2 moved the 1k draw
    by 49% at the same seed), so an unfrozen sample is unreproducible the moment
    anything upstream shifts.
    """
    path = output.with_name(output.stem + "_pmids.txt")
    how = (f"# Sampled: n={len(records)}, seed={seed}, stratified by disease category."
           if sampled else "# Frozen input: run from an explicit --pmids list.")
    path.write_text(
        f"# Frozen PMID list for {output.name}.\n"
        f"{how}\n"
        f"# Model: {spec.tag}. Written in output order — this is the *effective*\n"
        f"# sample: golden pmids, pmids without an abstract and failed LLM calls are\n"
        f"# already excluded, so re-running to retry failures can grow this list.\n"
        f"# Feed to run_silver.py --pmids to reproduce this run.\n"
        + "".join(r["pmid"] + "\n" for r in records),
        encoding="utf-8")
    return path


def process_one(pmid: str, text: str, qps: list[str], spec: ModelSpec,
                recanonicalize: bool = False) -> Optional[dict]:
    """Silver record for one abstract, or None if the LLM call failed.

    A failed call is deliberately **not** cached. Its empty result is
    indistinguishable from "this abstract mentions no pathway", and since the cache
    file is the resume key, caching it would bake the loss in permanently — every
    later run would skip the pmid. Returning None leaves it unprocessed so a re-run
    retries it.

    The cache is scoped per model (`<cache root>/<model slug>/<pmid>.json`). Keying
    on pmid alone would make a model swap replay the previous model's answers for
    every abstract already seen — a successful-looking run that cannot re-label.
    """
    model = spec.tag
    cache = cache_dir_for(spec) / f"{pmid}.json"
    if cache.exists():
        rec = json.loads(cache.read_text(encoding="utf-8"))
        if not recanonicalize:
            return rec
        rec = _annotate(_rebuild_from_cached(rec, text), text, pmid, model, qps)
        cache.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return rec

    try:
        llm_spans = extract_guided(text, qps, model=model)
    except LLMCallError as exc:
        log.warning("%s — LLM call failed, not cached (re-run to retry): %s", pmid, exc)
        return None
    merged = merge(llm_spans, boost(text))
    rec = _annotate(merged, text, pmid, model, qps)
    cache.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--number-of-articles", "--n", dest="n", type=int, default=1000,
                    metavar="N", help="how many articles to sample (ignored with --pmids)")
    ap.add_argument("--pmids", nargs="+", metavar="FILE",
                    help="run exactly the pmids in these file(s) — no sampling. Use to "
                         "reproduce a frozen sample, e.g. data/silver/pilot_1k_pmids.txt")
    ap.add_argument("--exclude", nargs="+", metavar="FILE", default=[],
                    help="never sample the pmids in these file(s); golden is excluded "
                         "unconditionally either way")
    ap.add_argument("--limit", type=int, default=None,
                    help="process only the first N of the sample (throughput check)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--output", default=str(OUTPUT_FILE))
    ap.add_argument("--recanonicalize", action="store_true",
                    help="re-derive canonical/match_type over the cache, no LLM calls "
                         "(use after changing llm/canonicalize.py)")
    ap.add_argument("--no-freeze", action="store_true",
                    help="skip writing <output stem>_pmids.txt")
    args = ap.parse_args()
    if args.pmids and args.exclude:
        ap.error("--exclude is meaningless with --pmids, which runs an explicit list "
                 "rather than sampling")

    spec = resolve(args.model)
    cache_dir = cache_dir_for(spec)
    cache_dir.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    qmap = load_query_pathways()
    abstracts = load_abstracts()
    cats = load_categories()

    if args.pmids:
        sample = load_pmid_files(args.pmids)
        # A golden pmid in an explicit list would put eval data into training data —
        # drop it here too, not just in the sampler.
        leaked = [p for p in sample if p in GOLDEN_PMIDS]
        if leaked:
            log.warning("Dropped %d GOLDEN pmid(s) from --pmids (never allowed in "
                        "silver): %s", len(leaked), ", ".join(leaked))
        missing = [p for p in sample
                   if p not in leaked and (p not in abstracts or p not in qmap)]
        if missing:
            log.warning("Dropped %d pmid(s) with no abstract/query-pathway data: %s%s",
                        len(missing), ", ".join(missing[:10]),
                        " …" if len(missing) > 10 else "")
        drop = set(leaked) | set(missing)
        sample = [p for p in sample if p not in drop]
        log.info("Sample: %d pmids from %d frozen file(s) — no sampling | model=%s",
                 len(sample), len(args.pmids), spec.tag)
    else:
        excluded = set(load_pmid_files(args.exclude))
        sample = select_sample(args.n, args.seed, qmap, abstracts, cats, exclude=excluded)
        log.info("Sample: %d pmids (golden + %d excluded, seed=%d) | model=%s",
                 len(sample), len(excluded), args.seed, spec.tag)
    log.info("Cache : %s", cache_dir)

    if args.limit:
        sample = sample[:args.limit]

    records, cached, failed = [], 0, 0
    t0 = time.time()
    for pmid in tqdm(sample, desc="Silver", unit="abstract"):
        was_cached = (cache_dir / f"{pmid}.json").exists()
        rec = process_one(pmid, abstracts[pmid], qmap[pmid], spec,
                          recanonicalize=args.recanonicalize)
        if rec is None:          # failed call — omitted, not cached, retried next run
            failed += 1
            continue
        records.append(rec)
        cached += was_cached

    elapsed = time.time() - t0
    with Path(args.output).open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # A --limit run is a throughput probe over the head of the sample, so freezing it
    # would pin a list that is not the sample anyone meant to draw.
    frozen = None
    if args.no_freeze:
        pass
    elif args.limit:
        log.warning("Not freezing pmids: --limit %d makes this a partial sample.",
                    args.limit)
    else:
        frozen = freeze_pmids(records, Path(args.output), spec, args.seed,
                              sampled=not args.pmids)

    # ---- stats ----------------------------------------------------------------
    spans = [s for r in records for s in r["spans"]]
    src = Counter(s["source"] for s in spans)
    mt = Counter(s["match_type"] for s in spans)
    unmapped = sum(1 for s in spans if s["canonical"] is None)
    fresh = len(sample) - cached - failed

    log.info("─" * 60)
    log.info("Output           : %s", args.output)
    if frozen:
        log.info("Frozen pmids     : %s", frozen)
    log.info("Model / cache    : %s  ->  %s", spec.tag, cache_dir)
    log.info("Abstracts        : %d/%d  (fresh %d, cached %d)",
             len(records), len(sample), fresh, cached)
    if failed:
        log.warning("LLM FAILURES     : %d — OUTPUT IS INCOMPLETE. These pmids were not "
                    "cached; re-run to retry them (the rest comes from cache).", failed)
    if fresh:
        log.info("Throughput       : %.1fs/abstract  -> 1k ≈ %.1f h",
                 elapsed / fresh, elapsed / fresh * 1000 / 3600)
    log.info("Spans            : %d  (%.1f per abstract)", len(spans),
             len(spans) / max(1, len(records)))
    log.info("  by source      : %s", dict(src))
    log.info("  by match_type  : %s", dict(mt))
    log.info("  unmapped       : %d (%.0f%%)  [golden baseline 16%%]",
             unmapped, 100 * unmapped / max(1, len(spans)))
    log.info("─" * 60)


if __name__ == "__main__":
    main()
