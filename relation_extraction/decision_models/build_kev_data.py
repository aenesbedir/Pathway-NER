#!/usr/bin/env python3
"""Turn silver relation pairs into Kev's labelled-request JSONL.

Each pair becomes one request: the abstract with its pathway and disease mentions
marked by prompts.mark_abstract, one `choice` question over the five v4 labels,
and the silver label. The criteria condense the label definitions and the
intervention rule of relation_extraction/prompts.py; the full guide is about
5,000 tokens and does not fit the lengths Kev trains on.

Usage (from the repository root, any Python 3):
    python relation_extraction/decision_models/build_kev_data.py \
        --outdir data/processed/relation/kev_silver
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = Path("/home/enes/pathway-re-synth/data/gold")

CRITERIA = {
    "upregulation": "The abstract states the pathway's activity, expression or flux is increased, activated or overexpressed in the disease. Also when inhibiting, blocking or depleting the pathway treats the disease.",
    "downregulation": "The abstract states the pathway is decreased, impaired, suppressed, deficient or defective in the disease, including inborn errors of that pathway. Also when activating, supplementing or restoring it treats the disease.",
    "association": "The abstract claims the pathway is changed or involved in the disease but states no direction: altered, dysregulated, perturbed, disturbed, associated with, implicated in.",
    "no_association_stated": "The abstract reports that it looked and found no relation between them.",
    "none": "The abstract makes no claim connecting this pathway to this disease: merely co-mentioned, or a context such as a cell line, another organism, a drug's metabolism or a definition sentence.",
}
INSTRUCTIONS = (
    "Which relation between the marked pathway and the marked disease does this "
    "abstract claim? Judge only this pair and use only what the abstract states."
)


def load_prompts():
    """Load prompts.py by path, so the script needs no package or dependencies."""
    path = ROOT / "relation_extraction/prompts.py"
    spec = importlib.util.spec_from_file_location("prompts", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def to_request(rec: dict, prompts) -> dict:
    mentions = [
        SimpleNamespace(label=label, start=m["start"], end=m["end"])
        for key, label in (("pathway", "PATHWAY"), ("disease", "DISEASE"))
        for m in rec[key]["mentions"]
    ]
    return {
        "state": {
            "abstract": prompts.mark_abstract(rec["paragraph"], mentions),
            "pathway": rec["pathway"]["canonical"],
            "disease": rec["disease"]["canonical"],
        },
        "questions": {
            "relation": {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": CRITERIA,
                "label": rec["class"],
            }
        },
        "_meta": {"rid": rec["id"]},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-dir", type=Path, default=DEFAULT_GOLD,
                    help="directory holding silver_train.jsonl and silver_dev.jsonl")
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()

    prompts = load_prompts()
    args.outdir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "dev"):
        n = 0
        with open(args.outdir / f"{split}.jsonl", "w") as out:
            for line in open(args.gold_dir / f"silver_{split}.jsonl"):
                out.write(json.dumps(to_request(json.loads(line), prompts), ensure_ascii=False) + "\n")
                n += 1
        print(split, n)


if __name__ == "__main__":
    main()
