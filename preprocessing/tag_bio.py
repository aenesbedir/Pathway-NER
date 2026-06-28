#!/usr/bin/env python3
"""
tag_bio.py — Step 4

Tokenizes text and aligns character-level spans from all_matches.jsonl
to per-token BIO labels using BiomedBERT's fast tokenizer.

Strategy:
  - Abstract spans  : tokenize the full abstract (fits within 512 tokens)
  - Full-text spans : extract a ±WINDOW_CHARS window around the span,
                      merging nearby spans into the same window

Label scheme:
  B-Pathway = 1  (first token of a pathway mention)
  I-Pathway = 2  (continuation token)
  O         = 0  (outside)
  -100           (special tokens and subword continuations — ignored by loss)

Input:
  data/processed/all_matches.jsonl
  data/raw/abstracts.jsonl
  data/processed/db_with_extracted_pathways.json   (text for recon3d records)

Output:
  data/processed/bio_tags.jsonl

Run with:
    python3 preprocessing/tag_bio.py
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from transformers import AutoTokenizer

ALL_MATCHES = Path("data/processed/all_matches.jsonl")
ABSTRACTS_FILE = Path("data/raw/abstracts.jsonl")
DB_FILE = Path("data/processed/db_with_extracted_pathways.json")
OUTPUT = Path("data/processed/bio_tags.jsonl")

MODEL = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"
MAX_TOKENS = 512
WINDOW_CHARS = 500  # chars on each side of a full-text span

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_articles() -> dict[str, dict]:
    articles = {}
    for line in ABSTRACTS_FILE.open(encoding="utf-8"):
        r = json.loads(line)
        articles[r["pmid"]] = r
    # Supplement with DB abstracts for recon3d records (different PMIDs)
    db = json.loads(DB_FILE.read_text(encoding="utf-8"))
    for rec in db:
        pmid = str(rec["pmid"])
        if pmid not in articles and rec.get("abstract"):
            articles[pmid] = {
                "pmid": pmid,
                "abstract": rec["abstract"],
                "full_text": "",
            }
    return articles


# ---------------------------------------------------------------------------
# BIO label helpers
# ---------------------------------------------------------------------------

def build_char_labels(text: str, spans: list[tuple[int, int]]) -> list[int]:
    """Return a char-level array: 0=O, 1=B, 2=I."""
    labels = [0] * len(text)
    for start, end in spans:
        if start < len(text) and end <= len(text):
            labels[start] = 1
            for j in range(start + 1, end):
                labels[j] = 2
    return labels


def tokenize_and_align(
    tokenizer,
    text: str,
    char_labels: list[int],
    pathway_ids: list[str],
    pmid: str,
    chunk: int,
) -> dict | None:
    encoding = tokenizer(
        text,
        max_length=MAX_TOKENS,
        truncation=True,
        return_offsets_mapping=True,
        return_attention_mask=True,
    )

    word_ids = encoding.word_ids()
    offset_mapping = encoding["offset_mapping"]

    token_labels = []
    prev_word_id = None

    for i, word_id in enumerate(word_ids):
        if word_id is None:
            # [CLS], [SEP], padding — ignore in loss
            token_labels.append(-100)
        elif word_id == prev_word_id:
            # Subword continuation — ignore in loss
            token_labels.append(-100)
        else:
            # First subword of a word — assign real label
            token_start = offset_mapping[i][0]
            cl = char_labels[token_start] if token_start < len(char_labels) else 0
            token_labels.append(cl)
        prev_word_id = word_id

    return {
        "pathway_ids": pathway_ids,
        "pmid": pmid,
        "chunk": chunk,
        "input_ids": encoding["input_ids"],
        "attention_mask": encoding["attention_mask"],
        "labels": token_labels,
    }


# ---------------------------------------------------------------------------
# Per-source processing
# ---------------------------------------------------------------------------

def process_abstract(
    tokenizer,
    pmid: str,
    article: dict,
    spans: list[dict],
    pathway_ids: list[str],
) -> dict | None:
    text = (article.get("abstract") or "").strip()
    if not text:
        return None
    char_labels = build_char_labels(text, [(s["start"], s["end"]) for s in spans])
    return tokenize_and_align(tokenizer, text, char_labels, pathway_ids, pmid, 0)


def process_fulltext(
    tokenizer,
    pmid: str,
    article: dict,
    spans: list[dict],
    pathway_ids: list[str],
) -> list[dict]:
    full_text = (article.get("full_text") or "").strip()
    if not full_text:
        return []

    results = []
    spans_sorted = sorted(spans, key=lambda s: s["start"])
    used = set()

    for i, span in enumerate(spans_sorted):
        if i in used:
            continue

        win_start = max(0, span["start"] - WINDOW_CHARS)
        win_end = min(len(full_text), span["end"] + WINDOW_CHARS)

        # Merge nearby spans into the same window
        window_spans = [span]
        for j, other in enumerate(spans_sorted):
            if j != i and j not in used:
                if other["start"] >= win_start and other["end"] <= win_end:
                    window_spans.append(other)
                    used.add(j)
        used.add(i)

        text_window = full_text[win_start:win_end]
        adj = [(s["start"] - win_start, s["end"] - win_start) for s in window_spans]
        char_labels = build_char_labels(text_window, adj)

        rec = tokenize_and_align(
            tokenizer, text_window, char_labels, pathway_ids, pmid, len(results)
        )
        if rec:
            results.append(rec)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Loading tokenizer: %s", MODEL)
    tokenizer = AutoTokenizer.from_pretrained(MODEL)

    log.info("Loading articles …")
    articles = load_articles()
    log.info("Articles loaded: %d", len(articles))

    # Group all_matches by pmid
    pmid_data: dict[str, dict] = defaultdict(
        lambda: {"pathway_ids": set(), "abstract_spans": [], "fulltext_spans": []}
    )
    skipped_no_spans = skipped_no_article = 0

    for line in ALL_MATCHES.open(encoding="utf-8"):
        r = json.loads(line)
        if not r["spans"]:
            skipped_no_spans += 1
            continue
        pmid = r["pmid"]
        if pmid not in articles:
            skipped_no_article += 1
            continue
        pmid_data[pmid]["pathway_ids"].add(r["pathway_id"])
        for span in r["spans"]:
            if span["source"] == "abstract":
                pmid_data[pmid]["abstract_spans"].append(span)
            else:
                pmid_data[pmid]["fulltext_spans"].append(span)

    log.info("PMIDs with spans     : %d", len(pmid_data))
    log.info("Skipped (no spans)   : %d", skipped_no_spans)
    log.info("Skipped (no article) : %d", skipped_no_article)

    written = abs_written = ft_written = 0

    with OUTPUT.open("w", encoding="utf-8") as out:
        for pmid, data in pmid_data.items():
            article = articles[pmid]
            pathway_ids = sorted(data["pathway_ids"])

            if data["abstract_spans"]:
                rec = process_abstract(
                    tokenizer, pmid, article, data["abstract_spans"], pathway_ids
                )
                if rec:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1
                    abs_written += 1

            for rec in process_fulltext(
                tokenizer, pmid, article, data["fulltext_spans"], pathway_ids
            ):
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
                ft_written += 1

    log.info("─" * 60)
    log.info("Output              : %s", OUTPUT)
    log.info("Total records       : %d", written)
    log.info("  — from abstract   : %d", abs_written)
    log.info("  — from full-text  : %d", ft_written)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
