#!/usr/bin/env python3
"""
export_doccano.py

Phase 3 / Faz 1d — turn silver span records (llm/run_silver.py) into a doccano
sequence-labeling import file.

Single label type: "Pathway". Reviewers accept / reject / fix the boundary of each
span and may add missed ones; they do NOT assign canonical names. `canonical`,
`match_type` and `source` ride along in `meta` as context only.

Reviewer instructions: data/silver/ANNOTATION_GUIDE.md

Input  : data/silver/pilot_1k.jsonl
Output : data/silver/pilot_1k_doccano.jsonl
    {"text": "<abstract>", "label": [[start, end, "Pathway"], ...], "meta": {...}}

Run from repo root:
    venv310/bin/python3 llm/export_doccano.py
    venv310/bin/python3 llm/export_doccano.py --limit 5 --output /tmp/smoke.jsonl
"""

import argparse
import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SILVER_FILE = ROOT / "data/silver/pilot_1k.jsonl"
ARTICLES_FILE = ROOT / "data/raw/articles.json"
OUTPUT_FILE = ROOT / "data/silver/pilot_1k_doccano.jsonl"

LABEL = "Pathway"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def load_abstracts() -> dict[str, str]:
    arts = json.loads(ARTICLES_FILE.read_text(encoding="utf-8"))
    return {str(a["pmid"]): (a.get("abstract") or "").strip() for a in arts}


def to_doccano(rec: dict, text: str) -> dict:
    labels, meta_spans = [], []
    for s in rec["spans"]:
        # Guard: never emit an offset that does not match the text we ship.
        if text[s["start"]:s["end"]] != s["text"]:
            log.warning("pmid %s: offset mismatch for %r — span dropped",
                        rec["pmid"], s["text"])
            continue
        labels.append([s["start"], s["end"], LABEL])
        meta_spans.append({
            "text": s["text"], "canonical": s["canonical"],
            "match_type": s["match_type"], "source": s["source"],
            "maybe_partial": s["maybe_partial"],
        })
    return {
        "text": text,
        "label": labels,
        "meta": {
            "pmid": rec["pmid"],
            "model": rec["model"],
            "query_pathways": rec["query_pathways"],
            "spans": meta_spans,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(SILVER_FILE))
    ap.add_argument("--output", default=str(OUTPUT_FILE))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    abstracts = load_abstracts()
    records = [json.loads(l) for l in Path(args.input).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        records = records[:args.limit]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_labels = 0
    with out.open("w", encoding="utf-8") as fh:
        for rec in records:
            d = to_doccano(rec, abstracts[rec["pmid"]])
            n_labels += len(d["label"])
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    log.info("─" * 60)
    log.info("Output    : %s", out)
    log.info("Documents : %d", len(records))
    log.info("Labels    : %d  (%.1f per document)", n_labels, n_labels / max(1, len(records)))
    log.info("Guide     : data/silver/ANNOTATION_GUIDE.md")
    log.info("─" * 60)


if __name__ == "__main__":
    main()
