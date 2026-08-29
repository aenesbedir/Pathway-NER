#!/usr/bin/env python3
"""
build_gt100_disease.py

Write the disease side of the gt_100 golden set as a file of its own.

`doccano/golden_dataset/gt_100.jsonl` holds only PATHWAY spans: those are the
human-reviewed ones. Its disease spans live in the 10,125-document corpus and
have to be joined back every time gt_100 is used for anything involving both
entity types, which is now most things. This script performs that join once and
saves the result beside gt_100.jsonl, in gt_100.jsonl's own shape.

The output is not gold. The pathway file earns that name; the disease spans are
raw output from `pruas/BENT-PubMedBERT-NER-Disease`, never reviewed, and the
model name is in the filename so that no reader mistakes one for the other. The
distinction is not academic - these spans include "inborn error", "failure" and
"dysfunction" as diseases, and they treat "ALL" and "acute lymphoblastic
leukemia" as two entities.

Offsets are copied unchanged. That is only sound because both files store the
same text for these PMIDs; the script asserts it rather than trusting it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path("/home/enes/NER-pipeline")
DEFAULT_GOLD = REPO / "doccano/golden_dataset/gt_100.jsonl"
DEFAULT_CORPUS = REPO / "data/doccano/disease_pathway_10125_doccano_combined_v1.jsonl"

#: Slug of the model that produced the spans, as used elsewhere in the repo
#: (`gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation.jsonl`).
DISEASE_MODEL = "bent-pubmedbert-ner-disease"
DISEASE_MODEL_ID = "pruas/BENT-PubMedBERT-NER-Disease"
DISEASE_MODEL_REVISION = "e70d6a5b1bd797b38092b0f2e4707ec36db9de59"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    out = args.out or args.gold.with_name(f"gt_100_disease_{DISEASE_MODEL}.jsonl")

    # Read line by line rather than str.splitlines(): the abstracts contain
    # Unicode line separators (U+2028 and friends) which splitlines() treats as
    # breaks and JSON does not, cutting records in half.
    def read_jsonl(path: Path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)

    gold = list(read_jsonl(args.gold))
    corpus = {str(r["meta"].get("pmid")): r for r in read_jsonl(args.corpus)}

    rows, n_spans, missing = [], 0, []
    for g in gold:
        pmid = str(g["meta"]["pmid"])
        src = corpus.get(pmid)
        if src is None:
            missing.append(pmid)
            continue
        if src["text"] != g["text"]:
            raise SystemExit(
                f"{pmid}: the two files store different text; offsets cannot be reused"
            )

        spans = sorted(
            (s for s in src["label"] if s[2] == "DISEASE"), key=lambda s: (s[0], s[1])
        )
        entities = []
        for i, (start, end, _label) in enumerate(spans, 1):
            entities.append(
                {
                    "id": i,
                    "label": "DISEASE",
                    "start_offset": start,
                    "end_offset": end,
                }
            )
        n_spans += len(entities)

        rows.append(
            {
                "id": g["id"],
                "text": g["text"],
                "meta": {
                    "pmid": pmid,
                    "source": src["meta"].get("source", str(args.corpus.name)),
                    "split": g["meta"].get("split"),
                    "annotator": DISEASE_MODEL_ID,
                    "annotator_revision": DISEASE_MODEL_REVISION,
                    "reviewed": False,
                    "spans": [
                        {
                            "text": g["text"][s[0] : s[1]],
                            "start": s[0],
                            "end": s[1],
                            "label": "DISEASE",
                        }
                        for s in spans
                    ],
                },
                "entities": entities,
                "relations": [],
                "Comments": [],
            }
        )

    if missing:
        raise SystemExit(f"{len(missing)} gt_100 PMIDs absent from the corpus: {missing[:5]}")

    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = {
        "purpose": "disease spans for the gt_100 PMIDs, joined out of the 10k corpus",
        "reviewed": False,
        "annotator": DISEASE_MODEL_ID,
        "annotator_revision": DISEASE_MODEL_REVISION,
        "pathway_side": str(args.gold),
        "pathway_side_sha256": sha256_file(args.gold),
        "disease_side": str(args.corpus),
        "disease_side_sha256": sha256_file(args.corpus),
        "n_documents": len(rows),
        "n_disease_spans": n_spans,
        "n_documents_without_disease": sum(1 for r in rows if not r["entities"]),
        "output": str(out),
        "output_sha256": sha256_file(out),
    }
    out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
