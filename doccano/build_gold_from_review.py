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

Review sources are converted to one gold file per corpus or pilot batch:

    wave2         5 batch reviews  -> doccano/wave2_1k_gold.jsonl
    wave3         5 batch reviews  -> doccano/wave3_1k_gold.jsonl
    wave4         5 batch reviews  -> doccano/wave4_1k_gold.jsonl
    pilot batches 01-03             -> doccano/pilot_1k_batchNN_gold.jsonl
    pilot batch05 1 review          -> doccano/pilot_1k_batch05_gold.jsonl

The five reviewed pilot batch gold files are also combined into
``doccano/pilot_1k_gold.jsonl``. Pilot batch 04 has no separate review JSON; its
tracked gold file is its review record and is preserved as-is.

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
    **{
        f"pilot_1k_batch{n:02d}_gold.jsonl": [
            (f"analysis/pilot_batch{n:02d}_review.json",
             f"doccano/batches/pilot_1k_doccano_batch_{n:02d}_5.jsonl"),
        ]
        for n in range(1, 4)
    },
    "wave2_1k_gold.jsonl": [
        (f"analysis/wave2_batch{n:02d}_review.json",
         f"doccano/batches/wave2_1k_doccano_batch_{n:02d}_5.jsonl")
        for n in range(1, 6)
    ],
    "wave3_1k_gold.jsonl": [
        (f"analysis/wave3_batch{n:02d}_review.json",
         f"doccano/batches/wave3_1k_doccano_batch_{n:02d}_5.jsonl")
        for n in range(1, 6)
    ],
    "wave4_1k_gold.jsonl": [
        (f"analysis/wave4_batch{n:02d}_review.json",
         f"doccano/batches/wave4_1k_doccano_batch_{n:02d}_5.jsonl")
        for n in range(1, 6)
    ],
    "pilot_1k_batch05_gold.jsonl": [
        ("analysis/batch_05_5_review.json",
         "doccano/batches/pilot_1k_doccano_batch_05_5.jsonl"),
    ],
}

PROVENANCE = {
    **{
        f"pilot_1k_batch{n:02d}_gold.jsonl": (
            "tp+fn (assistant-reviewed against ANNOTATION_GUIDE.md)"
        )
        for n in range(1, 4)
    },
    "wave2_1k_gold.jsonl": "tp+fn (assistant-reviewed against ANNOTATION_GUIDE.md)",
    "wave3_1k_gold.jsonl": "tp+fn (human-reviewed against ANNOTATION_GUIDE.md)",
    "wave4_1k_gold.jsonl": "tp+fn (human-reviewed against ANNOTATION_GUIDE.md)",
    "pilot_1k_batch05_gold.jsonl": (
        "tp+fn (mixed human and assistant review against ANNOTATION_GUIDE.md)"
    ),
}

# Wave-3/4 final gold files are tracked because their detailed review JSONs are
# local audit material. The default remains fully reproducible from a clean clone;
# use --include-local-reviews only where those audit files and batch intermediates
# are present.
DEFAULT_SOURCES = (
    "wave2_1k_gold.jsonl",
    "pilot_1k_batch01_gold.jsonl",
    "pilot_1k_batch02_gold.jsonl",
    "pilot_1k_batch03_gold.jsonl",
    "pilot_1k_batch05_gold.jsonl",
)

PILOT_GOLD_PARTS = tuple(
    f"pilot_1k_batch{n:02d}_gold.jsonl" for n in range(1, 6)
)


def load_texts(batch_path: Path) -> dict[str, str]:
    texts = {}
    for line in batch_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            texts[str(rec["meta"]["pmid"])] = rec["text"]
    return texts


def build_source(pairs, out_path: Path, provenance: str) -> None:
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
                    "gold": provenance,
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


def build_full_pilot(outdir: Path) -> None:
    rows = []
    pmids = set()
    span_count = 0
    for name in PILOT_GOLD_PARTS:
        path = outdir / name
        if name == "pilot_1k_batch04_gold.jsonl" and not path.exists():
            path = ROOT / "doccano" / name
        if not path.exists():
            raise SystemExit(f"missing reviewed pilot part: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            pmid = str(row["meta"]["pmid"])
            if pmid in pmids:
                raise SystemExit(f"duplicate pilot PMID while combining gold: {pmid}")
            pmids.add(pmid)
            for start, end, _label in row["label"]:
                if not (0 <= start < end <= len(row["text"])):
                    raise SystemExit(f"invalid pilot gold offset: {pmid} [{start}:{end}]")
            span_count += len(row["label"])
            rows.append(row)

    if len(rows) != 1000:
        raise SystemExit(f"expected 1000 reviewed pilot documents, found {len(rows)}")

    out_path = outdir / "pilot_1k_gold.jsonl"
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("%s: %d docs, %d gold spans", out_path.name, len(rows), span_count)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="doccano",
                    help="output directory (default: doccano)")
    ap.add_argument(
        "--include-local-reviews",
        action="store_true",
        help="also rebuild wave-3/4 from untracked local review audit files",
    )
    args = ap.parse_args()
    outdir = ROOT / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    selected = SOURCES if args.include_local_reviews else {
        name: SOURCES[name] for name in DEFAULT_SOURCES
    }
    for name, pairs in selected.items():
        build_source(pairs, outdir / name, PROVENANCE[name])
    build_full_pilot(outdir)


if __name__ == "__main__":
    main()
