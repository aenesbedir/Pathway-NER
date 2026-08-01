#!/usr/bin/env python3
"""
build_gold_from_review.py

Turn span-review JSONs (analysis/*_review.json) into doccano import files that
carry the *corrected gold* labels.

Gold spans for a document = its ``tp`` + ``fn`` entries: the true positives the
machine got right, plus the false negatives it missed. False positives are
dropped. This matches the gold definition already used by
``analysis/score_against_review.py``.

Output shape (doccano importer, label singular):

    {"text": "<abstract>", "label": [[start, end, "PATHWAY"], ...], "meta": {...}}

Two sources, two files (no PMID overlap between them):

    wave2         5 batch reviews  -> doccano/wave2_1k_gold.jsonl
    pilot batch05 1 review          -> doccano/pilot_1k_batch05_gold.jsonl

Text comes from the doccano batch files the reviews were built against; spans are
validated against that text (review offsets must reproduce the recorded string).

Run from repo root:
    venv310/bin/python3 doccano/build_gold_from_review.py
"""

import argparse
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABEL = "PATHWAY"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# (review json, batch jsonl the review scored) pairs per source.
SOURCES = {
    "wave2_1k_gold.jsonl": [
        (f"analysis/wave2_batch{n:02d}_review.json",
         f"doccano/batches/wave2_1k_doccano_batch_{n:02d}_5.jsonl")
        for n in range(1, 6)
    ],
    "pilot_1k_batch05_gold.jsonl": [
        ("analysis/batch_05_5_review.json",
         "doccano/batches/pilot_1k_doccano_batch_05_5.jsonl"),
    ],
}


def load_texts(batch_path: Path) -> dict[str, str]:
    texts = {}
    for line in batch_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            texts[str(rec["meta"]["pmid"])] = rec["text"]
    return texts


def build_source(pairs, out_path: Path) -> None:
    rows, n_docs, n_spans, errs = [], 0, 0, 0
    for review_rel, batch_rel in pairs:
        review = json.loads((ROOT / review_rel).read_text(encoding="utf-8"))
        texts = load_texts(ROOT / batch_rel)
        for d in review["documents"]:
            pmid = str(d["pmid"])
            text = texts[pmid]
            gold = sorted({(s["start"], s["end"]) for s in d["tp"] + d["fn"]})
            label = []
            for a, b in gold:
                snippet = next((s["text"] for s in d["tp"] + d["fn"]
                                if s["start"] == a and s["end"] == b), None)
                if snippet is not None and text[a:b] != snippet:
                    log.error("offset mismatch %s [%d:%d] %r != %r",
                              pmid, a, b, snippet, text[a:b])
                    errs += 1
                    continue
                label.append([a, b, LABEL])
            rows.append({
                "text": text,
                "label": label,
                "meta": {
                    "pmid": pmid,
                    "source": review_rel,
                    "gold": "tp+fn (assistant review vs ANNOTATION_GUIDE.md)",
                },
            })
            n_docs += 1
            n_spans += len(label)

    if errs:
        raise SystemExit(f"{errs} offset mismatch(es); aborting {out_path.name}")

    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    log.info("%s: %d docs, %d gold spans", out_path.name, n_docs, n_spans)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="doccano",
                    help="output directory (default: doccano)")
    args = ap.parse_args()
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    for name, pairs in SOURCES.items():
        build_source(pairs, outdir / name)


if __name__ == "__main__":
    main()
