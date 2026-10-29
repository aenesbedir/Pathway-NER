#!/usr/bin/env python3
"""
compare_query_string_vs_predicted.py

Quality-control check on the 10k combined corpus: every abstract was retrieved
by a PubMed query of the form

    ("<pathway>"[Title/Abstract]) AND ("<disease>"[Title/Abstract])

so we know at least one pathway term and one disease term co-occur with the
article. This script measures whether the silver annotations actually contain
those query terms.

Per entity type (PATHWAY, DISEASE) and per abstract:

  exact match  - at least one annotated span whose normalized token set equals
                 the normalized token set of one of the query terms for that
                 PMID. Token-set equality makes the check order-insensitive so
                 inverted MeSH forms ("Carcinoma, Hepatocellular") match
                 natural word order ("hepatocellular carcinoma").
  word overlap - at least one annotated span sharing >=1 content word with a
                 query term for that PMID. Generic words (pathway, metabolism,
                 disease, and, of, ...) are excluded; trailing "s" is stripped
                 so singular/plural forms compare equal.

Caveat: the PubMed query matched Title OR Abstract, while the doccano text is
the abstract only. A query term appearing only in the title is a legitimate
miss here, so the numbers below are a lower bound on query-term coverage.

Inputs:
  data/raw/pathway_disease_pairs.json
  data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl

Run:
  cd /home/enes/NER-pipeline
  python3 scripts/compare_query_string_vs_predicted.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

PAIRS_FILE = Path("data/raw/pathway_disease_pairs.json")
DOCCANO_FILE = Path("data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl")

# Generic words that must not count as evidence of a term match on their own.
STOPWORDS = {
    # connectives / function words
    "and", "or", "of", "the", "in", "with", "to", "a", "an", "for", "type",
    # pathway-generic
    "pathway", "pathways", "signaling", "signalling", "metabolism", "metabolic",
    "cycle", "synthesis", "biosynthesis", "degradation", "transport",
    # disease-generic
    "disease", "diseases", "disorder", "disorders", "syndrome", "syndromes",
    "neoplasm", "neoplasms", "cancer", "cancers", "carcinoma", "tumor",
    "tumors", "tumour", "tumours", "deficiency", "injury",
}


def tokens(text: str) -> set[str]:
    """Lowercase content-word token set with naive plural stripping."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w.rstrip("s") or w for w in words}


_STOP_NORM = {w.rstrip("s") or w for w in STOPWORDS}


def main() -> None:
    pairs = json.loads(PAIRS_FILE.read_text())
    query_terms: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"pathway": set(), "disease": set()}
    )
    for p in pairs:
        for pmid in p["pmids"]:
            query_terms[pmid]["pathway"].add(p["pathway"])
            query_terms[pmid]["disease"].add(p["disease_name"])

    stats = {
        kind: {
            "docs": 0,           # docs with a PMID present in the pair file
            "no_spans": 0,       # of those, docs with zero spans of this kind
            "exact": 0,
            "word_overlap": 0,   # includes exact matches
            "missed_in_text": 0,  # no overlap, yet a query term occurs verbatim in the abstract
        }
        for kind in ("pathway", "disease")
    }
    label_key = {"pathway": "PATHWAY", "disease": "DISEASE"}
    miss_examples = {"pathway": [], "disease": []}
    docs_total = 0
    docs_without_pair = 0

    with DOCCANO_FILE.open() as f:
        for line in f:
            doc = json.loads(line)
            docs_total += 1
            pmid = str(doc.get("meta", {}).get("pmid", ""))
            if pmid not in query_terms:
                docs_without_pair += 1
                continue
            text = doc["text"]
            for kind in ("pathway", "disease"):
                st = stats[kind]
                st["docs"] += 1
                spans = [
                    text[s[0]:s[1]]
                    for s in doc.get("label", [])
                    if s[2] == label_key[kind]
                ]
                terms = query_terms[pmid][kind]
                if not spans:
                    st["no_spans"] += 1
                    text_lower = text.lower()
                    if any(term.lower() in text_lower for term in terms):
                        st["missed_in_text"] += 1
                    continue
                span_token_sets = [tokens(s) for s in spans]
                exact = any(
                    ts == tokens(term) for ts in span_token_sets for term in terms
                )
                span_all = set().union(*span_token_sets)
                span_content = span_all - _STOP_NORM
                overlap = False
                for term in terms:
                    term_content = tokens(term) - _STOP_NORM
                    if term_content:
                        if span_content & term_content:
                            overlap = True
                            break
                    # Term made of generic words only (e.g. "Carcinoma"):
                    # fall back to its raw tokens so it can still match.
                    elif span_all & tokens(term):
                        overlap = True
                        break
                if exact:
                    st["exact"] += 1
                if exact or overlap:
                    st["word_overlap"] += 1
                else:
                    text_lower = text.lower()
                    in_text = any(term.lower() in text_lower for term in terms)
                    if in_text:
                        st["missed_in_text"] += 1
                    if len(miss_examples[kind]) < 5:
                        miss_examples[kind].append(
                            {
                                "pmid": pmid,
                                "query_terms": sorted(terms),
                                "spans": spans[:6],
                                "term_in_abstract": in_text,
                            }
                        )

    print(f"docs in corpus:            {docs_total}")
    print(f"docs without a query pair: {docs_without_pair}")
    for kind in ("pathway", "disease"):
        st = stats[kind]
        docs = st["docs"]
        with_spans = docs - st["no_spans"]
        print(f"\n== {kind.upper()} ==")
        print(f"docs with query terms:              {docs}")
        print(f"  docs with zero {kind} spans:      {st['no_spans']} ({st['no_spans']/docs:.1%})")
        print(f"  exact query-term match:           {st['exact']} ({st['exact']/docs:.1%})")
        print(f"  >=1 content-word overlap:         {st['word_overlap']} ({st['word_overlap']/docs:.1%})")
        if with_spans:
            print(f"  overlap among docs with spans:    {st['word_overlap']/with_spans:.1%}")
        missed = docs - st["word_overlap"]
        print(f"  no overlap at all:                {missed} ({missed/docs:.1%})")
        print(f"    of which term occurs verbatim in abstract (likely annotation miss): {st['missed_in_text']}")
        if miss_examples[kind]:
            print("  sample misses (spans present, no overlap):")
            for ex in miss_examples[kind]:
                print(
                    f"    pmid {ex['pmid']}: query={ex['query_terms']} spans={ex['spans']}"
                    f" term_in_abstract={ex['term_in_abstract']}"
                )


if __name__ == "__main__":
    main()
