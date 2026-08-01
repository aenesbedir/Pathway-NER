#!/usr/bin/env python3
"""
tag_bio.py — Step 4

Tokenizes text and aligns character-level spans from a matches JSONL file
to per-token BIO labels, using the fast tokenizer of whichever base encoder
`--model` names (see `encoders.py`).

Strategy:
  - Abstract spans  : tokenize the full abstract (one record per document)
  - Full-text spans : extract a ±WINDOW_CHARS window around the span,
                      merging nearby spans into the same window

Label scheme:
  B-Pathway = 1  (first token of a pathway mention)
  I-Pathway = 2  (continuation token)
  O         = 0  (outside)
  -100           (special tokens and subword continuations — ignored by loss)

Alignment
---------
A word-initial token carries a label; every continuation subword is -100. The
label comes from the token's character **range**, not from a single character
of it:

    B  if some span s has  token.start <= s.start < token.end
    I  elif some span s overlaps the token
    O  otherwise

The range test matters because `offset_mapping[i][0]` is not portable. Measured
on Bio-ModernBERT, the token `Ġfatty` reports offsets `(10, 16)` covering
`' fatty'` — the leading space is inside the token, despite `trim_offsets: true`
in its `tokenizer.json` (that flag governs the post-processor, not the ByteLevel
pre-tokenizer). A point lookup at character 10 reads the space, labels the token
`O`, and the span disappears with nothing raised. The range test asks whether the
span *begins anywhere inside* the token instead, which is true regardless.

WordPiece offsets do start at the word, so this is a measured no-op there: 0 of
1083 records change against the previous point-lookup output.

The `<=` in the B test is what preserves nested spans. The gold data annotates
shared-head enumerations twice — `cholesterol and fatty acid synthesis` and
`fatty acid synthesis` — and flat BIO cannot represent that. Opening a new `B`
wherever an inner span starts is the behaviour gold-001…008 trained on; changing
it is a modelling decision, not a tokenizer fix.

Default (gold data):
  venv310/bin/python3 preprocessing/tag_bio.py \\
      --matches  data/processed/gold/matches.jsonl \\
      --articles data/processed/gold/articles.jsonl \\
      --output   data/processed/gold-biomedbert-base/bio_tags.jsonl \\
      --db "" --model biomedbert-base

Articles file can be JSONL (one record per line) or a JSON array.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from encoders import resolve, vocab_fingerprint  # noqa: E402

WINDOW_CHARS = 500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_articles(articles_path: Path, db_path: Path | None = None) -> dict[str, dict]:
    """Load articles from a JSONL or JSON-array file, keyed by str(pmid)."""
    articles: dict[str, dict] = {}
    raw = articles_path.read_text(encoding="utf-8").strip()

    if raw.startswith("["):
        records = json.loads(raw)
    else:
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]

    for r in records:
        pmid = str(r.get("pmid", ""))
        if pmid:
            articles[pmid] = r

    # Phase 1 supplement: DB abstracts for recon3d records
    if db_path and db_path.exists():
        db = json.loads(db_path.read_text(encoding="utf-8"))
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

def usable_spans(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Drop spans that fall outside the text — offsets can come from a longer source."""
    return [(s, e) for s, e in spans if s < len(text) and e <= len(text)]


def label_for_token(a: int, b: int, spans: list[tuple[int, int]]) -> int:
    """BIO label for the token covering characters [a, b). See module docstring."""
    label = 0
    for start, end in spans:
        if a < end and start < b:          # overlaps this span
            if a <= start < b:             # ... and contains where it begins
                return 1                   # B — wins over any I
            label = 2                      # I — keep looking for a B
    return label


def tokenize_and_align(
    tokenizer,
    text: str,
    spans: list[tuple[int, int]],
    pathway_ids: list[str],
    pmid: str,
    chunk: int,
    max_tokens: int,
) -> dict | None:
    encoding = tokenizer(
        text,
        max_length=max_tokens,
        truncation=True,
        return_offsets_mapping=True,
        return_attention_mask=True,
    )

    word_ids = encoding.word_ids()
    offset_mapping = encoding["offset_mapping"]

    token_labels = []
    prev_word_id = None

    for i, word_id in enumerate(word_ids):
        if word_id is None or word_id == prev_word_id:
            token_labels.append(-100)
        else:
            a, b = offset_mapping[i]
            token_labels.append(label_for_token(a, b, spans))
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

def process_abstract(tokenizer, pmid, article, spans, pathway_ids, max_tokens):
    text = (article.get("abstract") or "").strip()
    if not text:
        return None
    usable = usable_spans(text, [(s["start"], s["end"]) for s in spans])
    return tokenize_and_align(tokenizer, text, usable, pathway_ids, pmid, 0, max_tokens)


def process_fulltext(tokenizer, pmid, article, spans, pathway_ids, max_tokens):
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

        window_spans = [span]
        for j, other in enumerate(spans_sorted):
            if j != i and j not in used:
                if other["start"] >= win_start and other["end"] <= win_end:
                    window_spans.append(other)
                    used.add(j)
        used.add(i)

        text_window = full_text[win_start:win_end]
        adj = [(s["start"] - win_start, s["end"] - win_start) for s in window_spans]

        rec = tokenize_and_align(
            tokenizer, text_window, usable_spans(text_window, adj),
            pathway_ids, pmid, len(results), max_tokens,
        )
        if rec:
            results.append(rec)

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--matches",
        default="data/processed/all_matches.jsonl",
        help="Input matches JSONL (default: Phase 1 all_matches.jsonl)",
    )
    parser.add_argument(
        "--articles",
        default="data/raw/abstracts.jsonl",
        help="Articles file: JSONL or JSON array (default: Phase 1 abstracts.jsonl)",
    )
    parser.add_argument(
        "--output",
        default="data/processed/bio_tags.jsonl",
        help="Output BIO tags JSONL (default: data/processed/bio_tags.jsonl)",
    )
    parser.add_argument(
        "--db",
        default="data/processed/db_with_extracted_pathways.json",
        help="Optional DB supplement for Phase 1 recon3d records",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Encoder registry key or HF id (see `python3 encoders.py`); "
             "decides the tokenizer and the truncation length",
    )
    args = parser.parse_args()

    spec = resolve(args.model)

    matches_path = Path(args.matches)
    articles_path = Path(args.articles)
    output_path = Path(args.output)
    db_path = Path(args.db) if args.db else None

    log.info("Matches  : %s", matches_path)
    log.info("Articles : %s", articles_path)
    log.info("Output   : %s", output_path)
    log.info("Model    : %s  (ctx %d)", spec.hf_id, spec.max_tokens)

    log.info("Loading tokenizer: %s", spec.tokenizer_id)
    tokenizer = spec.load_tokenizer()
    if not tokenizer.is_fast:
        raise SystemExit(f"{spec.tokenizer_id} has no fast tokenizer — "
                         "offset_mapping and word_ids are required for alignment")

    log.info("Loading articles...")
    articles = load_articles(articles_path, db_path)
    log.info("Articles loaded: %d", len(articles))

    pmid_data: dict[str, dict] = defaultdict(
        lambda: {"pathway_ids": set(), "abstract_spans": [], "fulltext_spans": []}
    )
    skipped_no_spans = skipped_no_article = 0

    for line in matches_path.open(encoding="utf-8"):
        r = json.loads(line)
        if not r.get("spans"):
            skipped_no_spans += 1
            continue
        pmid = str(r["pmid"])
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = abs_written = ft_written = 0

    with output_path.open("w", encoding="utf-8") as out:
        for pmid, data in pmid_data.items():
            article = articles[pmid]
            pathway_ids = sorted(data["pathway_ids"])

            if data["abstract_spans"]:
                rec = process_abstract(
                    tokenizer, pmid, article, data["abstract_spans"], pathway_ids,
                    spec.max_tokens,
                )
                if rec:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1
                    abs_written += 1

            for rec in process_fulltext(
                tokenizer, pmid, article, data["fulltext_spans"], pathway_ids,
                spec.max_tokens,
            ):
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
                ft_written += 1

    # meta.json travels with the input_ids so train.py can refuse a mismatched
    # model. Vocabularies overlap in range, so a wrong pairing raises nothing
    # on its own — it just trains a worse model.
    import transformers

    meta = {
        "model_key": args.model or "biomedbert-base",
        "hf_id": spec.hf_id,
        "tokenizer_id": spec.tokenizer_id,
        "tokenizer_class": type(tokenizer).__name__,
        "vocab_size": tokenizer.vocab_size,
        "vocab_fingerprint": vocab_fingerprint(tokenizer),
        "max_tokens": spec.max_tokens,
        "transformers_version": transformers.__version__,
        "n_records": written,
    }
    meta_path = output_path.parent / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    log.info("─" * 60)
    log.info("Total records       : %d", written)
    log.info("  — from abstract   : %d", abs_written)
    log.info("  — from full-text  : %d", ft_written)
    log.info("─" * 60)
    log.info("Wrote %s", meta_path)


if __name__ == "__main__":
    main()
