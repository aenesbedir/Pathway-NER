#!/usr/bin/env python3
"""
run_silver.py

Phase 3 / Faz 1c — produce variation-aware **silver** span labels over a sample of
abstracts. The default is the config chosen in Faz 0 (P3-0c/d):
    qwen2.5:14b, no-vocab + lenient + synonyms, plus the deterministic booster.

Flow per abstract:
    annotator + boost()  ->  merge()  ->  canonicalize()  ->  spans

**The annotator is a parameter.** `--model` takes either an ollama tag (the LLM
path, unchanged) or the path of a fine-tuned NER checkpoint directory, e.g.

    --model runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7

which runs that token classifier instead. Everything after extraction is identical
either way, because the booster, merge(), canonicalize() and the cache all work on
character-offset spans and never ask where a span came from. See llm/annotators.py
for the interface and how the two are told apart (a disk check, not a flag).

Which to use is a measured question, not a preference: on gt_100 the 10k-trained
biom-electra-large checkpoint scores exact-span F1 0.836 against the LLM silver's
0.769, the gap being almost entirely recall (doccano/golden_dataset/gt_100_scores.json).

Silver is machine-labeled and noisy — it goes to doccano for human review before it
is trusted for training. It is kept strictly apart from the gold set
(playground/golden_set/).

**The 10 golden PMIDs (v1: 5, v2: +5) are excluded from the sample.** Since silver
becomes training data, including any gold PMID would mean training on our own eval set.

Input  : data/processed/exact_matches.jsonl  (pmid -> query pathways, --matches)
         data/raw/articles.json              (abstracts, --articles)
         data/raw/pathway_disease_pairs.json (disease category for stratification,
                                              --pairs; unused with --pmids)
         Only the abstracts are required. Query pathways are an LLM prompt hint and
         record metadata — no NER checkpoint reads them — so `--matches none` runs a
         corpus that has none rather than dropping every pmid for lack of them.
Output : data/silver/pilot_1k.jsonl (--output)
         plus <output stem>_pmids.txt — the effective sample, in output order, ready
         to feed back as --pmids. Written every run except --limit (a partial head of
         the sample) and --no-freeze.
Cache  : data/raw/llm_cache_silver/{annotator}/{pmid}.json  (resumable — a 1k LLM
         run is ~2h; a NER run is minutes, and caches mostly to keep --recanonicalize
         working the same way).
         Scoped per annotator on purpose: keyed on pmid alone, swapping the model
         replayed the previous model's answers for every abstract already seen, so a
         re-label run looked successful and changed nothing. Config per LLM lives in
         llm/models.py; a checkpoint's slug is derived from its path.
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

    # another corpus, labelled by the NER checkpoint instead of the LLM
    venv310/bin/python3 llm/run_silver.py \\
        --model runs-truba-checkpoints/pathway-10k/biom-electra-large/lr3e-05/seed7 \\
        --articles data/raw/kegg_recon3d/articles.json --matches none \\
        --pmids data/raw/kegg_recon3d/pmids.txt \\
        --output data/processed/kegg_recon3d/pathway-10k-biom-electra-large-seed7_abstracts_1521.jsonl
"""

import argparse
import hashlib
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

from annotators import resolve_annotator  # noqa: E402
from booster import boost, merge  # noqa: E402
from canonicalize import canonicalize, match_type_for  # noqa: E402
from extract_guided import LLMCallError  # noqa: E402
from models import DEFAULT  # noqa: E402

MATCHES_FILE = ROOT / "data/processed/exact_matches.jsonl"
ARTICLES_FILE = ROOT / "data/raw/articles.json"
PAIRS_FILE = ROOT / "data/raw/pathway_disease_pairs.json"
OUTPUT_FILE = ROOT / "data/silver/pilot_1k.jsonl"
CACHE_ROOT = ROOT / "data/raw/llm_cache_silver"

MODEL = DEFAULT

# Golden-set PMIDs — excluded so silver never trains on the eval set.
# Keep in sync with playground/golden_set/build_golden_set.py (PMIDS_V1 + PMIDS_V2)
# and playground/golden_set/golden_pmids.txt (v1 + v2 + v3).
GOLDEN_PMIDS = {
    # v1
    "11469814",
    "29615816",
    "36294866",
    "39934780",
    "40225847",
    # v2
    "34376485",
    "42299101",
    "28587170",
    "38669820",
    "37807318",
    # v3 — 100 test-split docs of the 10k corpus, in doccano review
    # (doccano/golden_100_doccano.jsonl). Not yet in golden_set.json; excluded
    # now so review time cannot leak them into silver.
    "10079102",
    "11861404",
    "15677459",
    "15908045",
    "15946046",
    "16188953",
    "1635807",
    "17124394",
    "1898255",
    "19570878",
    "20583850",
    "22180458",
    "22185841",
    "22265211",
    "23121637",
    "23377617",
    "23580368",
    "23811272",
    "26741399",
    "27312339",
    "29373083",
    "29514138",
    "29622725",
    "29792360",
    "30112875",
    "30386262",
    "30622605",
    "30740736",
    "30906627",
    "30993483",
    "31029786",
    "31130824",
    "31219974",
    "31384818",
    "31385097",
    "31493765",
    "31956867",
    "32183836",
    "3271614",
    "32732914",
    "33491741",
    "33552904",
    "33645231",
    "33663989",
    "34147638",
    "34737767",
    "34850407",
    "3503558",
    "35133277",
    "35341850",
    "36296329",
    "36426594",
    "36517247",
    "36531023",
    "36547099",
    "36834531",
    "36979028",
    "37269349",
    "37379970",
    "37538846",
    "37806604",
    "37809388",
    "3871414",
    "38740741",
    "38901285",
    "38974325",
    "39076904",
    "39245190",
    "39252446",
    "39350090",
    "39752405",
    "39906671",
    "40025393",
    "40176362",
    "40277908",
    "40377860",
    "40395817",
    "40812694",
    "41061307",
    "41471909",
    "41560327",
    "41577073",
    "41652287",
    "41703645",
    "41752037",
    "41810983",
    "41833755",
    "41839945",
    "41872128",
    "42094521",
    "42135764",
    "42253805",
    "42299884",
    "42316281",
    "6409386",
    "7675237",
    "856442",
    "8748156",
    "8811168",
    "9792200",

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


def load_query_pathways(path: Optional[Path] = None) -> dict[str, list[str]]:
    """pmid -> query pathway names.

    `exact_matches.jsonl` carries `pathway_id: null` rows (pairs Step 2 found no span
    for), which must not leak into the prompt hints or the export metadata.

    Returns `{}` when no matches file is given. Query pathways are an LLM prompt hint
    (llm/extract_guided.py) and metadata; a corpus that has none — or an annotator
    that does not read the abstract's retrieval query, i.e. every NER checkpoint —
    runs fine without them, so their absence must not silently drop every pmid.
    """
    path = path or MATCHES_FILE
    if path is None:
        return {}
    by_pmid: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                if r.get("pathway_id"):
                    by_pmid[str(r["pmid"])].add(r["pathway_id"])
                else:
                    by_pmid.setdefault(str(r["pmid"]), set())
    return {k: sorted(v) for k, v in by_pmid.items()}


def load_categories(path: Optional[Path] = None) -> dict[str, str]:
    """pmid -> primary disease category (deterministic when a pmid has several).

    Only the stratified sampler uses this; a `--pmids` run never touches it, which
    is why a missing pairs file is not an error.
    """
    path = path or PAIRS_FILE
    if path is None or not path.exists():
        return {}
    cats: dict[str, set[str]] = defaultdict(set)
    for rec in json.loads(path.read_text(encoding="utf-8")):
        for pmid in rec.get("pmids", []):
            cats[str(pmid)].add(rec["disease_category"])
    return {p: sorted(c)[0] for p, c in cats.items()}


def load_abstracts(path: Optional[Path] = None, field: str = "abstract") -> dict[str, str]:
    """pmid -> text, from a JSON array or a JSONL file.

    `field` is which key holds the text. It exists because the same annotator is
    also pointed at corpora that are not abstracts — PMC full text lives under
    `full_text`, and the doccano exports carry `text`. Naming the field beats
    copying a corpus into an `abstract` key it does not belong in.

    JSONL is accepted alongside the `articles.json` array so a doccano export can
    be fed straight in; the pmid is read from the record or from its `meta` block,
    which is where doccano keeps it.
    """
    path = path or ARTICLES_FILE
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        records = json.loads(raw)
    out: dict[str, str] = {}
    for rec in records:
        pmid = rec.get("pmid") or rec.get("meta", {}).get("pmid")
        if pmid is None:
            continue
        out[str(pmid)] = (rec.get(field) or "").strip()
    return out


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


def _annotate(spans: list[dict], text: str, pmid: str, model: str, qps: list[str],
              source: str = "llm_silver") -> dict:
    """Derive canonical/match_type from raw (surface, offset, source) spans.

    Cheap and deterministic — kept separate from the LLM call so that a canonicalizer
    change can be re-applied over the cache without paying for inference again
    (see --recanonicalize).

    `source` names the annotator that produced the non-booster spans ("llm_silver"
    for the Ollama path, "ner:<checkpoint>" for a token classifier), so a record
    always says what wrote it.
    """
    out = []
    for s in spans:
        if s.get("source") == "booster":
            canonical = s["canonical"]          # the booster knows what it searched for
            mtype = match_type_for(s["surface"], canonical)
            span_source = "booster"
        else:
            canonical, mtype = canonicalize(s["surface"])
            span_source = source
        out.append({
            "start": s["start"], "end": s["end"], "text": s["surface"],
            "canonical": canonical, "match_type": mtype, "source": span_source,
        })
    return {"pmid": pmid, "model": model, "text_sha": text_sha(text),
            "query_pathways": qps, "spans": out}


def _rebuild_from_cached(rec: dict, text: str, booster: bool = True) -> list[dict]:
    """Rebuild raw spans from cache without calling the annotator again.

    Only the annotator's own spans are recovered from cache — the booster is re-run
    from scratch (pure regex, free) because its own canonical assignment is baked
    into the cached record and must not survive a booster change. merge() is
    re-applied too. The test is "not booster" rather than a specific source string,
    so it holds for every annotator.
    """
    model_spans = [{"surface": s["text"], "start": s["start"], "end": s["end"]}
                   for s in rec["spans"] if s["source"] != "booster"]
    return merge(model_spans, boost(text)) if booster else model_spans


def cache_dir_for(annotator) -> Path:
    return CACHE_ROOT / annotator.cache_slug


def text_sha(text: str) -> str:
    """Short digest of the text a cached record was produced from.

    The cache is keyed on pmid, which silently assumes one text per pmid. That
    broke the moment the same pmid was run over its abstract and then over its PMC
    full text: the full-text run reported "cached" and replayed the abstract's
    spans. Storing the digest makes a changed text a cache miss, which is what it
    always should have been.

    Records written before this field existed are accepted with a warning: every
    one of them came from data/raw/articles.json abstracts, so they are valid for
    that corpus and re-running them would cost hours of LLM calls.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def freeze_pmids(records: list[dict], output: Path, annotator, seed: int,
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
        f"# Model: {annotator.tag}. Written in output order — this is the *effective*\n"
        f"# sample: golden pmids, pmids without an abstract and failed LLM calls are\n"
        f"# already excluded, so re-running to retry failures can grow this list.\n"
        f"# Feed to run_silver.py --pmids to reproduce this run.\n"
        + "".join(r["pmid"] + "\n" for r in records),
        encoding="utf-8")
    return path


_LEGACY_CACHE_WARNED = set()


def cache_file_for(annotator, pmid: str, text: str) -> Path:
    """Where this (annotator, pmid, text) is cached, or was cached before.

    New records are written as `{pmid}-{text_sha}.json`. The digest is in the name,
    not only in the record, so the same pmid can be held for several texts at once —
    an abstract run and a full-text run of the same corpus no longer overwrite each
    other's answers on every alternation.

    A legacy `{pmid}.json` is still read when no digest-named file exists: those
    were all written from data/raw/articles.json abstracts, and re-running them
    would cost hours of LLM calls.
    """
    d = cache_dir_for(annotator)
    keyed = d / f"{pmid}-{text_sha(text)}.json"
    if keyed.exists():
        return keyed
    legacy = d / f"{pmid}.json"
    if legacy.exists() and _is_legacy(legacy):
        return legacy
    return keyed


def _is_legacy(cache: Path) -> bool:
    """True for a pre-digest record, which is trusted for the abstracts corpus."""
    try:
        rec = json.loads(cache.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if rec.get("text_sha") is not None:
        return False
    slug = cache.parent.name
    if slug not in _LEGACY_CACHE_WARNED:
        _LEGACY_CACHE_WARNED.add(slug)
        log.warning("%s: cache records carry no text_sha — accepting them as "
                    "abstracts of data/raw/articles.json, which is where every "
                    "such record came from.", slug)
    return True


def process_batch(items: list[tuple[str, str, list[str]]], annotator,
                  booster: bool = True,
                  recanonicalize: bool = False) -> list[Optional[dict]]:
    """Records for a batch of (pmid, text, query_pathways), None where a call failed.

    Cached pmids never reach the annotator, so a batch is only as large as its
    uncached members. The annotator sees one call for the whole batch — that is the
    point for a GPU-batched NER checkpoint; the LLM annotator declares batch_size 1
    so a failed generation stays attributable to its own pmid.

    Failure handling mirrors the single-call rule below: a raised LLMCallError marks
    every item of that batch as failed rather than caching an empty answer.
    """
    out: list[Optional[dict]] = [None] * len(items)
    pending: list[int] = []
    for i, (pmid, text, qps) in enumerate(items):
        cache = cache_file_for(annotator, pmid, text)
        if cache.exists():
            # What the cache holds is the *annotator's* answer; the booster and the
            # canonicalizer are re-derived on every read. They are free (regex and
            # string matching) and, unlike the model call, their output depends on
            # settings that change between runs — a `--no-booster` run reading a
            # cache written with the booster on would otherwise silently replay the
            # booster's spans.
            rec = _annotate(
                _rebuild_from_cached(json.loads(cache.read_text(encoding="utf-8")),
                                     text, booster),
                text, pmid, annotator.tag, qps, source=annotator.source)
            if recanonicalize:
                cache.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            out[i] = rec
            continue
        if recanonicalize:      # nothing cached to re-derive; never call the model
            continue
        pending.append(i)

    if not pending:
        return out

    try:
        produced = annotator.spans_batch(
            [(items[i][1], items[i][2]) for i in pending])
    except LLMCallError as exc:
        log.warning("%s — annotator call failed, not cached (re-run to retry): %s",
                    ", ".join(items[i][0] for i in pending), exc)
        return out

    for i, spans in zip(pending, produced):
        pmid, text, qps = items[i]
        merged = merge(spans, boost(text)) if booster else spans
        rec = _annotate(merged, text, pmid, annotator.tag, qps, source=annotator.source)
        cache_file_for(annotator, pmid, text).write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        out[i] = rec
    return out




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
    ap.add_argument("--model", default=MODEL,
                    help="ollama registry key/tag (LLM annotator, the default) OR a "
                         "path to a fine-tuned NER checkpoint directory, e.g. "
                         "runs-truba-checkpoints/pathway-10k/biom-electra-large/"
                         "lr3e-05/seed7. The dispatch is a disk check — see "
                         "llm/annotators.py")
    ap.add_argument("--articles", default=None, metavar="FILE",
                    help=f"abstracts in articles.json shape (default {ARTICLES_FILE})")
    ap.add_argument("--matches", default=None, metavar="FILE",
                    help=f"pmid -> query pathways, exact_matches.jsonl shape (default "
                         f"{MATCHES_FILE}). Pass 'none' for a corpus without them: "
                         f"they are an LLM prompt hint, and no NER checkpoint reads "
                         f"them")
    ap.add_argument("--text-field", default="abstract", metavar="KEY",
                    help="which record key holds the text (default 'abstract'; use "
                         "'full_text' for PMC full text, 'text' for a doccano export)")
    ap.add_argument("--all", action="store_true",
                    help="run every pmid in --articles, in file order — no sampling "
                         "and no pmid list. For evaluating a whole corpus")
    ap.add_argument("--allow-golden", action="store_true",
                    help="do NOT drop GOLDEN_PMIDS. Silver is training data, so the "
                         "golden set is excluded unconditionally to keep the eval set "
                         "out of it; this flag is for the opposite job — *scoring* an "
                         "annotator against gt_100, where the golden pmids are the "
                         "point. Never pass it on a run whose output becomes training "
                         "data")
    ap.add_argument("--pairs", default=None, metavar="FILE",
                    help=f"disease categories for stratified sampling, unused with "
                         f"--pmids (default {PAIRS_FILE})")
    ap.add_argument("--output", default=str(OUTPUT_FILE))
    ap.add_argument("--batch-size", type=int, default=None,
                    help="override the annotator's batch size (NER only; the LLM "
                         "annotator is one request per abstract by construction)")
    ap.add_argument("--no-booster", dest="booster", action="store_false",
                    help="skip the deterministic recall booster (llm/booster.py). It "
                         "was tuned to patch LLM recall gaps; a NER checkpoint may "
                         "not need it — measure before assuming either way")
    ap.add_argument("--recanonicalize", action="store_true",
                    help="re-derive canonical/match_type over the cache, no model "
                         "calls (use after changing llm/canonicalize.py)")
    ap.add_argument("--no-freeze", action="store_true",
                    help="skip writing <output stem>_pmids.txt")
    args = ap.parse_args()
    if args.all and (args.pmids or args.exclude):
        ap.error("--all runs the whole --articles file; it takes neither --pmids nor "
                 "--exclude")
    if args.pmids and args.exclude:
        ap.error("--exclude is meaningless with --pmids, which runs an explicit list "
                 "rather than sampling")

    ner_kwargs = {"batch_size": args.batch_size} if args.batch_size else {}
    annotator = resolve_annotator(args.model, **ner_kwargs)
    cache_dir = cache_dir_for(annotator)
    cache_dir.mkdir(parents=True, exist_ok=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    matches_file = (None if (args.matches or "").lower() == "none"
                    else Path(args.matches) if args.matches else MATCHES_FILE)
    qmap = load_query_pathways(matches_file)
    abstracts = load_abstracts(Path(args.articles) if args.articles else None,
                               field=args.text_field)
    cats = load_categories(Path(args.pairs) if args.pairs else None)

    if args.pmids or args.all:
        sample = ([p for p in abstracts if abstracts[p]] if args.all
                  else load_pmid_files(args.pmids))
        # A golden pmid in an explicit list would put eval data into training data —
        # drop it here too, not just in the sampler. --allow-golden is the deliberate
        # exception, for scoring runs whose output is never trained on.
        leaked = [] if args.allow_golden else [p for p in sample if p in GOLDEN_PMIDS]
        if args.allow_golden:
            log.warning("--allow-golden: GOLDEN_PMIDS are NOT excluded. This output "
                        "must not become training data.")
        if leaked:
            log.warning("Dropped %d GOLDEN pmid(s) from --pmids (never allowed in "
                        "silver): %s", len(leaked), ", ".join(leaked))
        # Only the abstract is required. A pmid absent from qmap simply has no query
        # pathways — an empty hint for the LLM, nothing at all for a NER checkpoint.
        missing = [p for p in sample if p not in leaked and p not in abstracts]
        if missing:
            log.warning("Dropped %d pmid(s) with no abstract: %s%s",
                        len(missing), ", ".join(missing[:10]),
                        " …" if len(missing) > 10 else "")
        drop = set(leaked) | set(missing)
        sample = [p for p in sample if p not in drop]
        log.info("Sample: %d pmids %s | model=%s", len(sample),
                 "from --all (whole corpus)" if args.all
                 else f"from {len(args.pmids)} frozen file(s) — no sampling",
                 annotator.tag)
    else:
        excluded = set(load_pmid_files(args.exclude))
        pool = qmap or {p: [] for p in abstracts}
        sample = select_sample(args.n, args.seed, pool, abstracts, cats, exclude=excluded)
        log.info("Sample: %d pmids (golden + %d excluded, seed=%d) | model=%s",
                 len(sample), len(excluded), args.seed, annotator.tag)
    log.info("Annotator: %s | input window %s | booster %s",
             annotator, annotator.max_input, "on" if args.booster else "off")
    log.info("Cache : %s", cache_dir)

    if args.limit:
        sample = sample[:args.limit]

    batch_size = getattr(annotator, "batch_size", 1)
    records, cached, failed = [], 0, 0
    t0 = time.time()
    with tqdm(total=len(sample), desc="Silver", unit="abstract") as bar:
        for i in range(0, len(sample), batch_size):
            chunk = sample[i:i + batch_size]
            # Existence under the pmid alone is not a hit — the text has to match.
            was_cached = [cache_file_for(annotator, p, abstracts[p]).exists()
                          for p in chunk]
            out = process_batch(
                [(p, abstracts[p], qmap.get(p, [])) for p in chunk],
                annotator, booster=args.booster, recanonicalize=args.recanonicalize)
            for rec, hit in zip(out, was_cached):
                if rec is None:   # failed call — omitted, not cached, retried next run
                    failed += 1
                    continue
                records.append(rec)
                cached += hit
            bar.update(len(chunk))

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
        frozen = freeze_pmids(records, Path(args.output), annotator, args.seed,
                              sampled=not (args.pmids or args.all))

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
    log.info("Model / cache    : %s  ->  %s", annotator.tag, cache_dir)
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
