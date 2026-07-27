#!/usr/bin/env python3
"""
gold_to_matches.py — Step 3b (review-to-gold pipeline)

Bridge between the doccano gold files (doccano/build_gold_from_review.py) and
``tag_bio.py``. Converts gold spans into the two inputs ``tag_bio`` expects:

    matches.jsonl   {"pmid", "pathway_id": "gold",
                     "spans": [{"start", "end", "source": "abstract"}, ...]}
    articles.jsonl  {"pmid", "abstract": <text>, "full_text": ""}

``matches`` holds only docs with ≥1 span (``tag_bio`` skips span-free lines
anyway); ``articles`` holds every doc so the text is always available.

Sources must not share a PMID — a duplicate aborts the run rather than silently
merging two label sets.

Run from repo root:
    venv310/bin/python3 preprocessing/gold_to_matches.py \\
        --sources doccano/wave2_1k_gold.jsonl doccano/pilot_1k_batch05_gold.jsonl \\
        --outdir  data/processed/gold
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", nargs="+", required=True,
                    help="doccano gold jsonl file(s)")
    ap.add_argument("--outdir", default="data/processed/gold",
                    help="output directory (default: data/processed/gold)")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    matches, articles, seen = [], [], set()
    n_spans = 0
    for src in args.sources:
        for line in Path(src).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            pmid = str(r["meta"]["pmid"])
            if pmid in seen:
                raise SystemExit(f"duplicate pmid {pmid} across sources; aborting")
            seen.add(pmid)
            articles.append({"pmid": pmid, "abstract": r["text"], "full_text": ""})
            spans = [{"start": a, "end": b, "source": "abstract"}
                     for a, b, _ in r["label"]]
            if spans:
                matches.append({"pmid": pmid, "pathway_id": "gold", "spans": spans})
                n_spans += len(spans)

    (outdir / "matches.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in matches),
        encoding="utf-8")
    (outdir / "articles.jsonl").write_text(
        "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in articles),
        encoding="utf-8")

    log.info("articles: %d  matches(docs with spans): %d  spans: %d",
             len(articles), len(matches), n_spans)


if __name__ == "__main__":
    main()
