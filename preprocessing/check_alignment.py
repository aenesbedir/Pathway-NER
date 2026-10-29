#!/usr/bin/env python3
"""
check_alignment.py — round-trip validation of BIO alignment

Decodes `bio_tags.jsonl` back to character spans and compares them against the
gold spans in `matches.jsonl`. Run it once per tokenizer, before trusting any
number produced with that tokenizer.

Why this exists
---------------
`tag_bio.py` labels a token from its character range (`offset_mapping`). That is
an assumption about the tokenizer, and every tokenizer family breaks it
differently: SentencePiece can report the leading space as part of a token,
ByteLevel BPE splits on a different regex than WordPiece, and a larger vocabulary
puts more of a word into a single token. None of those failures raise — they
produce a slightly worse label set, and the resulting F1 reads as a verdict on
the encoder. This script turns that class of silent failure into an exit code.

Categories
----------
Each gold span is one of:
  exact       — decoded back with identical boundaries
  boundary    — decoded, but the boundaries moved (the span does not sit on word
                boundaries, so the label lands on the enclosing words)
  truncated   — begins past the tokenizer's cut; unavoidable, reported not failed
  nested      — overlaps another gold span. Flat BIO cannot hold two overlapping
                mentions, so one of them is always lost. Reported, not failed:
                the gold data annotates shared-head enumerations twice
                (`cholesterol and fatty acid synthesis` *and* `fatty acid
                synthesis`), and resolving that is a modelling decision.
  LOST        — none of the above. This is the failure mode; exit code 1.

Also prints the B / I / O / -100 counts, because `CLASS_WEIGHTS` in `train.py`
was tuned against WordPiece token statistics. A 50k BPE vocabulary masks fewer
continuation subwords and shifts the B:I:O ratio, so the weights deserve a fresh
look per tokenizer family rather than an assumption.

Run from repo root:
    venv310/bin/python3 preprocessing/check_alignment.py \\
        --data-dir data/processed/gold-biomedbert-base \\
        --model    biomedbert-base \\
        --report   analysis/alignment_biomedbert-base.json
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from encoders import resolve  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def word_extents(encoding) -> list[tuple[int, int, int]]:
    """(index of the word-initial token, char start, char end) per word.

    Labels live on word-initial tokens only, so a span's character extent runs
    from the start of its first word to the end of its last.
    """
    words: list[tuple[int, int, int]] = []
    prev = None
    for i, word_id in enumerate(encoding.word_ids()):
        if word_id is None:
            prev = None
            continue
        a, b = encoding["offset_mapping"][i]
        if word_id == prev:
            first, start, _ = words[-1]
            words[-1] = (first, start, b)
        else:
            words.append((i, a, b))
        prev = word_id
    return words


def decode_spans(labels: list[int], words: list[tuple[int, int, int]],
                 text: str) -> list[tuple[int, int]]:
    """BIO-decode to character spans. `I` without a preceding `B` opens a span
    (the lenient rule `playground/golden_set/eval_bert_model.py` decodes with).

    Character ranges are trimmed of surrounding whitespace. A ByteLevel BPE
    tokenizer reports a word's leading space as part of the token — measured on
    Bio-ModernBERT, `Ġfatty` spans `' fatty'`, not `'fatty'` — regardless of the
    `trim_offsets` flag in its `tokenizer.json`. That offset is what makes the
    range-based label assignment in `tag_bio.py` necessary, and it is also why a
    decoded span has to be stripped before it can be compared to a gold one.
    """
    spans: list[list[int]] = []
    open_span = False
    for token_i, start, end in words:
        label = labels[token_i]
        if label == 1 or (label == 2 and not open_span):
            spans.append([start, end])
            open_span = True
        elif label == 2:
            spans[-1][1] = end
        else:
            open_span = False

    trimmed = []
    for a, b in spans:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        trimmed.append((a, b))
    return trimmed


def overlaps(x: tuple[int, int], y: tuple[int, int]) -> bool:
    return x[0] < y[1] and y[0] < x[1]


# The [UNK] rate is mostly a *measurement*, not a defect: a general-domain
# vocabulary on biomedical text legitimately produces more of them, and that
# penalty is part of what the domain axis is meant to quantify (measured on the
# gold set: BiomedBERT 0.23%, BioBERT 0.68%, general BERT 0.64%, SciBERT 1.09%).
# The threshold is therefore set to catch a *broken* pairing — the wrong tokenizer
# entirely — not a domain mismatch.
MAX_UNK_RATE = 5.0          # percent of tokens
# Above this many tokens per whitespace word, the text is being shredded. English
# biomedical text runs ~1.5-2.5 depending on the vocabulary; 4+ means the
# tokenizer is falling back to characters.
MAX_TOKENS_PER_WORD = 4.0


def tokenizer_health(tokenizer, texts: list[str], spec) -> tuple[dict, list[str]]:
    """Checks that span-recovery is structurally blind to.

    Alignment validates that gold spans survive the round trip, and offsets stay
    correct however badly the text is tokenized — so a tokenizer can shred every
    word and still score 95% exact. That is not hypothetical: BioBERT
    (`dmis-lab/biobert-base-cased-v1.2`) ships no `tokenizer_config.json` at all,
    so AutoTokenizer defaults to `do_lower_case=True` on a *cased* checkpoint,
    turning `Alzheimer` into `al ##z ##heimer` — and it passed the alignment check
    at 95.8%. Note that neither the UNK rate (1.57% broken vs 1.55% fixed) nor
    tokens-per-word (1.811 vs 1.836) moves enough to catch it; only the
    cased-vocabulary check does. These exist because of that.
    """
    unk_id = tokenizer.unk_token_id
    n_tokens = n_unk = n_words = 0
    for text in texts:
        ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        n_tokens += len(ids)
        if unk_id is not None:
            n_unk += sum(i == unk_id for i in ids)
        n_words += len(text.split())

    vocab = tokenizer.get_vocab()
    has_capitals = sum(1 for token in vocab if any(c.isupper() for c in token))
    lowercases = bool(getattr(tokenizer, "do_lower_case", False))

    stats = {
        "unk_rate_pct": round(100 * n_unk / n_tokens, 4) if n_tokens else 0.0,
        "tokens_per_word": round(n_tokens / n_words, 3) if n_words else 0.0,
        "vocab_size": len(vocab),
        "vocab_entries_with_capitals": has_capitals,
        "do_lower_case": lowercases,
    }

    problems = []
    if stats["unk_rate_pct"] > MAX_UNK_RATE:
        problems.append(
            f"{stats['unk_rate_pct']:.2f}% of tokens are [UNK] (limit "
            f"{MAX_UNK_RATE}%) — the vocabulary does not cover this corpus"
        )
    if stats["tokens_per_word"] > MAX_TOKENS_PER_WORD:
        problems.append(
            f"{stats['tokens_per_word']:.2f} tokens per word (limit "
            f"{MAX_TOKENS_PER_WORD}) — the text is being shredded into characters"
        )
    # A cased vocabulary fed lowercased input: every capitalised entry is dead
    # weight the model was pretrained on and will now never see.
    if lowercases and has_capitals > 0.05 * len(vocab):
        problems.append(
            f"cased vocabulary ({has_capitals} of {len(vocab)} entries contain "
            f"capitals) but do_lower_case=True — the model can never reach those "
            f"entries. Set tokenizer_kwargs={{'do_lower_case': False}} on the "
            f"'{spec.data_slug}' registry entry"
        )
    return stats, problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True,
                    help="Directory holding bio_tags.jsonl for one tokenizer")
    ap.add_argument("--matches", default="data/processed/gold/matches.jsonl")
    ap.add_argument("--articles", default="data/processed/gold/articles.jsonl")
    ap.add_argument("--splits", default="data/processed/gold/splits.json",
                    help="Used only to report how many records fall outside the "
                         "frozen split")
    ap.add_argument("--model", default=None, help="Encoder registry key or HF id")
    ap.add_argument("--report", default=None, help="Optional JSON report path")
    args = ap.parse_args()

    spec = resolve(args.model)
    tokenizer = spec.load_tokenizer()

    articles = {str(json.loads(l)["pmid"]): json.loads(l)["abstract"]
                for l in Path(args.articles).open(encoding="utf-8")}
    gold: dict[str, list[tuple[int, int]]] = {}
    for line in Path(args.matches).open(encoding="utf-8"):
        r = json.loads(line)
        gold[str(r["pmid"])] = [(s["start"], s["end"]) for s in r["spans"]]

    records = [json.loads(l) for l in
               (Path(args.data_dir) / "bio_tags.jsonl").open(encoding="utf-8")]

    counts = Counter()
    labels_seen = Counter()
    failures, boundary_cases, nested_pairs, mid_word = [], [], [], []

    for rec in records:
        pmid = str(rec["pmid"])
        text = articles[pmid]
        spans = gold.get(pmid, [])

        encoding = tokenizer(text, max_length=spec.max_tokens, truncation=True,
                             return_offsets_mapping=True)
        if list(encoding["input_ids"]) != list(rec["input_ids"]):
            raise SystemExit(
                f"pmid {pmid}: bio_tags.jsonl was produced by a different "
                f"tokenizer than {spec.tokenizer_id} — regenerate it"
            )

        for label in rec["labels"]:
            labels_seen[label] += 1

        words = word_extents(encoding)
        decoded = decode_spans(rec["labels"], words, text)
        covered = max((b for _, _, b in words), default=0)

        for start, end in spans:
            if (start, end) in decoded:
                counts["exact"] += 1
                continue

            hit = next((d for d in decoded if overlaps((start, end), d)), None)
            if hit is not None:
                counts["boundary"] += 1
                boundary_cases.append({
                    "pmid": pmid, "gold": text[start:end],
                    "decoded": text[hit[0]:hit[1]],
                    "context": text[max(0, start - 30):end + 30],
                })
                continue

            if start >= covered:
                counts["truncated"] += 1
                continue

            if any((s, e) != (start, end) and overlaps((start, end), (s, e))
                   for s, e in spans):
                counts["nested"] += 1
                continue

            counts["LOST"] += 1
            failures.append({"pmid": pmid, "span": text[start:end],
                             "start": start, "end": end,
                             "context": text[max(0, start - 30):end + 30]})

        # Annotation-quality findings, independent of the tokenizer.
        for i, (start, end) in enumerate(spans):
            for other in spans[i + 1:]:
                if overlaps((start, end), other):
                    nested_pairs.append({"pmid": pmid,
                                         "outer": text[start:end],
                                         "inner": text[other[0]:other[1]]})
            starts_mid = start > 0 and text[start - 1].isalnum() and text[start].isalnum()
            ends_mid = end < len(text) and text[end].isalnum() and text[end - 1].isalnum()
            if starts_mid or ends_mid:
                mid_word.append({"pmid": pmid, "span": text[start:end],
                                 "where": "start" if starts_mid else "end",
                                 "context": text[max(0, start - 30):end + 30]})

    total = sum(counts.values())
    log.info("─" * 66)
    log.info("Tokenizer : %s  (ctx %d, vocab %d)",
             spec.tokenizer_id, spec.max_tokens, tokenizer.vocab_size)
    log.info("Records   : %d", len(records))
    log.info("Gold spans: %d", total)
    for key in ("exact", "boundary", "truncated", "nested", "LOST"):
        log.info("  %-10s %5d  (%.1f%%)", key, counts[key],
                 100 * counts[key] / total if total else 0)
    log.info("─" * 66)
    log.info("Label counts (B / I / O / -100): %d / %d / %d / %d",
             labels_seen[1], labels_seen[2], labels_seen[0], labels_seen[-100])
    supervised = labels_seen[0] + labels_seen[1] + labels_seen[2]
    log.info("  supervised positions: %d   positive rate: %.2f%%",
             supervised,
             100 * (labels_seen[1] + labels_seen[2]) / supervised if supervised else 0)
    health, problems = tokenizer_health(
        tokenizer, [articles[str(r["pmid"])] for r in records], spec)
    log.info("─" * 66)
    log.info("Tokenizer health (what span recovery cannot see):")
    log.info("  [UNK] rate        : %.4f%%", health["unk_rate_pct"])
    log.info("  tokens per word   : %.3f", health["tokens_per_word"])
    log.info("  vocab / capitals  : %d / %d   do_lower_case=%s",
             health["vocab_size"], health["vocab_entries_with_capitals"],
             health["do_lower_case"])
    log.info("─" * 66)
    log.info("Annotation findings (tokenizer-independent, for wave-3 review):")
    log.info("  nested span pairs : %d", len(nested_pairs))
    log.info("  mid-word spans    : %d", len(mid_word))

    if args.report:
        report = {
            "tokenizer": spec.tokenizer_id, "max_tokens": spec.max_tokens,
            "vocab_size": tokenizer.vocab_size, "n_records": len(records),
            "counts": dict(counts),
            "label_counts": {"B": labels_seen[1], "I": labels_seen[2],
                             "O": labels_seen[0], "ignored": labels_seen[-100]},
            "tokenizer_health": health, "tokenizer_problems": problems,
            "lost": failures, "boundary": boundary_cases,
            "nested_pairs": nested_pairs, "mid_word_spans": mid_word,
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
        log.info("Report written to %s", args.report)

    failed = False
    if counts["LOST"]:
        log.error("%d spans lost for no explainable reason — first 5:", counts["LOST"])
        for f in failures[:5]:
            log.error("  pmid %s  %r  in  %r", f["pmid"], f["span"], f["context"])
        failed = True

    for problem in problems:
        log.error("TOKENIZER: %s", problem)
        failed = True

    if failed:
        raise SystemExit(1)

    log.info("OK — every gold span is accounted for, tokenizer is healthy.")


if __name__ == "__main__":
    main()
