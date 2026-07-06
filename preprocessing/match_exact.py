#!/usr/bin/env python3
"""
match_exact.py

Case-insensitive exact matching of pathway names over article abstracts and
full texts using SpaCy PhraseMatcher.

Supported pathway sources (add new loaders to SOURCES to extend):
  - "recon"    : unique_pathways_from_recon.json  (flat name list, no IDs)
  - "kegg"     : data/raw/kegg_pathways.jsonl
  - "reactome" : data/raw/reactome_pathways.jsonl

Usage:
  python3 preprocessing/match_exact.py --sources recon
  python3 preprocessing/match_exact.py --sources recon kegg reactome

Input  : data/raw/articles.json
Output : data/processed/exact_matches.jsonl
"""

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

import spacy
from spacy.matcher import PhraseMatcher

ARTICLES_FILE = Path("data/raw/articles.json")
OUTPUT_FILE   = Path("data/processed/exact_matches.jsonl")

MIN_TERM_LEN  = 4   # skip terms shorter than this (characters)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pathway loaders — each loader returns list[dict]:
#   {"pathway_id": str, "canonical_name": str, "synonyms": list[str]}
# ---------------------------------------------------------------------------

def load_recon() -> list[dict]:
    path = Path("unique_pathways_from_recon.json")
    names = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"pathway_id": name, "canonical_name": name, "synonyms": []}
        for name in names
    ]


def load_kegg() -> list[dict]:
    path = Path("data/raw/kegg_pathways.jsonl")
    pathways = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            pathways.append({
                "pathway_id":     r["pathway_id"],
                "canonical_name": r["canonical_name"],
                "synonyms":       r.get("synonyms", []),
            })
    return pathways


def load_reactome() -> list[dict]:
    path = Path("data/raw/reactome_pathways.jsonl")
    pathways = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            pathways.append({
                "pathway_id":     r["pathway_id"],
                "canonical_name": r["canonical_name"],
                "synonyms":       r.get("synonyms", []),
            })
    return pathways


SOURCES = {
    "recon":    load_recon,
    "kegg":     load_kegg,
    "reactome": load_reactome,
}


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------

def build_matcher(
    nlp: spacy.Language,
    pathways: list[dict],
) -> tuple[PhraseMatcher, dict[str, list[str]]]:
    """Build a single PhraseMatcher from all pathway names and synonyms.
    Also returns a term_text → [pathway_id, ...] mapping."""
    term_to_ids: dict[str, list[str]] = defaultdict(list)
    for pw in pathways:
        pid = pw["pathway_id"]
        terms = [pw["canonical_name"]] + pw.get("synonyms", [])
        for term in terms:
            term = term.strip()
            if len(term) >= MIN_TERM_LEN:
                term_to_ids[term].append(pid)

    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    for term in term_to_ids:
        matcher.add(term, [nlp.make_doc(term)])

    log.info("Unique terms in matcher: %d", len(term_to_ids))
    return matcher, dict(term_to_ids)


# ---------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------

def keep_longest(spans: list[dict]) -> list[dict]:
    spans = sorted(spans, key=lambda s: s["end"] - s["start"], reverse=True)
    kept = []
    for span in spans:
        if not any(k["start"] <= span["start"] and span["end"] <= k["end"] for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s["start"])


def find_spans(
    nlp: spacy.Language,
    matcher: PhraseMatcher,
    term_to_ids: dict[str, list[str]],
    text: str,
    source: str,
) -> list[dict]:
    doc = nlp(text)
    raw = []
    for match_id, start, end in matcher(doc):
        term       = nlp.vocab.strings[match_id]
        span_start = doc[start].idx
        span_end   = doc[end - 1].idx + len(doc[end - 1].text)
        for pid in term_to_ids.get(term, []):
            raw.append({
                "start":      span_start,
                "end":        span_end,
                "text":       doc[start:end].text,
                "pathway_id": pid,
                "source":     source,
            })
    return keep_longest(raw)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["recon"],
        choices=list(SOURCES),
        help="Pathway sources to use (default: recon)",
    )
    args = parser.parse_args()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading spaCy model: en_core_sci_sm")
    nlp = spacy.load("en_core_sci_sm", disable=["ner", "parser"])

    # Load pathways from selected sources
    pathways: list[dict] = []
    for src in args.sources:
        loaded = SOURCES[src]()
        log.info("  %-10s → %d pathways", src, len(loaded))
        pathways.extend(loaded)
    log.info("Total pathways: %d", len(pathways))

    matcher, term_to_ids = build_matcher(nlp, pathways)

    log.info("Loading articles: %s", ARTICLES_FILE)
    articles = json.loads(ARTICLES_FILE.read_text(encoding="utf-8"))
    log.info("Articles: %d", len(articles))

    written = with_spans = total_spans = 0

    with OUTPUT_FILE.open("w", encoding="utf-8") as out:
        for i, article in enumerate(articles):
            pmid      = article["pmid"]
            abstract  = (article.get("abstract") or "").strip()
            full_text = (article.get("full_text") or "").strip()

            all_spans: list[dict] = []
            if abstract:
                all_spans += find_spans(nlp, matcher, term_to_ids, abstract, "abstract")
            if full_text:
                all_spans += find_spans(nlp, matcher, term_to_ids, full_text, "full_text")

            # Group spans by pathway_id
            by_pathway: dict[str, list[dict]] = defaultdict(list)
            for span in all_spans:
                pid = span.pop("pathway_id")
                by_pathway[pid].append(span)

            if by_pathway:
                for pid, spans in by_pathway.items():
                    out.write(json.dumps(
                        {"pmid": pmid, "pathway_id": pid, "spans": spans},
                        ensure_ascii=False,
                    ) + "\n")
                    written += 1
                    with_spans += 1
                    total_spans += len(spans)
            else:
                # No spans found — write empty record for downstream LLM step
                out.write(json.dumps(
                    {"pmid": pmid, "pathway_id": None, "spans": []},
                    ensure_ascii=False,
                ) + "\n")
                written += 1

            if (i + 1) % 500 == 0:
                log.info("  %d / %d articles processed", i + 1, len(articles))

    log.info("─" * 60)
    log.info("Sources       : %s", ", ".join(args.sources))
    log.info("Output        : %s", OUTPUT_FILE)
    log.info("Records       : %d", written)
    log.info("With spans    : %d", with_spans)
    log.info("No spans      : %d", written - with_spans)
    log.info("Total spans   : %d", total_spans)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
