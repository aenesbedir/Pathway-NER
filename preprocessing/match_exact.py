#!/usr/bin/env python3
"""
match_exact.py  —  Step 2

Runs SpaCy PhraseMatcher over each article (abstract + full_text) to find
exact/case-insensitive mentions of pathway names and synonyms.

All (pathway, pmid) pairs are written to output regardless of match count.
Pairs with no spans are passed to Step 3 (LLM matching).

Input  : data/processed/pathway_abstract_pairs.jsonl
         data/raw/abstracts.jsonl
Output : data/processed/exact_matches.jsonl

Run with the project venv:
    venv310/bin/python3 match_exact.py
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher

PAIRS_FILE = Path("data/processed/pathway_abstract_pairs.jsonl")
ABSTRACTS_FILE = Path("data/raw/abstracts.jsonl")
OUTPUT_FILE = Path("data/processed/exact_matches.jsonl")

SPACY_MODEL = "en_core_sci_sm"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def load_abstracts() -> dict[str, dict]:
    abstracts = {}
    with ABSTRACTS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            abstracts[rec["pmid"]] = rec
    return abstracts


def load_pairs() -> dict[str, list[dict]]:
    """Group pairs by pmid → list of pathway records."""
    by_pmid: dict[str, list[dict]] = defaultdict(list)
    with PAIRS_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            pair = json.loads(line)
            by_pmid[pair["pmid"]].append(pair)
    return by_pmid


def keep_longest(spans: list[dict]) -> list[dict]:
    """Remove spans that are fully contained within a longer span."""
    spans = sorted(spans, key=lambda s: s["end"] - s["start"], reverse=True)
    kept = []
    for span in spans:
        if not any(k["start"] <= span["start"] and span["end"] <= k["end"] for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s["start"])


def find_spans(
    nlp: spacy.Language,
    matcher: PhraseMatcher,
    text: str,
    source: str,
) -> list[dict]:
    doc = nlp(text)
    matches = matcher(doc)
    spans = []
    for _, start, end in matches:
        spans.append({
            "start": doc[start].idx,
            "end": doc[end - 1].idx + len(doc[end - 1].text),
            "text": doc[start:end].text,
            "source": source,
        })
    return keep_longest(spans)


def build_matcher(nlp: spacy.Language, pathway: dict) -> PhraseMatcher:
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    terms = [pathway["canonical_name"]] + pathway.get("synonyms", [])
    patterns = [nlp.make_doc(t) for t in terms if t.strip()]
    matcher.add("PATHWAY", patterns)
    return matcher


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading spaCy model: %s", SPACY_MODEL)
    nlp = spacy.load(SPACY_MODEL, disable=["ner", "parser"])

    log.info("Loading abstracts …")
    abstracts = load_abstracts()

    log.info("Loading pathway-pmid pairs …")
    by_pmid = load_pairs()

    total_pairs = sum(len(v) for v in by_pmid.values())
    log.info("Total pairs: %d across %d articles", total_pairs, len(by_pmid))

    written = 0
    with_spans = 0
    total_spans = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for pmid, pathways in by_pmid.items():
            article = abstracts.get(pmid, {})
            abstract_text = article.get("abstract") or ""
            full_text = article.get("full_text") or ""

            for pathway in pathways:
                matcher = build_matcher(nlp, pathway)
                spans = []

                if abstract_text:
                    spans += find_spans(nlp, matcher, abstract_text, "abstract")
                if full_text:
                    spans += find_spans(nlp, matcher, full_text, "full_text")

                out.write(json.dumps({
                    "pathway_id": pathway["pathway_id"],
                    "source": pathway["source"],
                    "pmid": pmid,
                    "spans": spans,
                }, ensure_ascii=False) + "\n")

                written += 1
                if spans:
                    with_spans += 1
                    total_spans += len(spans)

    log.info("─" * 60)
    log.info("Output          : %s", OUTPUT_FILE)
    log.info("Pairs written   : %d", written)
    log.info("With spans      : %d (%.1f%%)", with_spans, 100 * with_spans / written)
    log.info("No spans        : %d → goes to Step 3", written - with_spans)
    log.info("Total spans     : %d", total_spans)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
