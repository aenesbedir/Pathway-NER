#!/usr/bin/env python3
"""Turn silver relation pairs into Kev's labelled-request JSONL.

Each pair becomes one request: the abstract with its pathway and disease mentions
marked by prompts.mark_abstract, one `choice` question over the five v4 labels,
and the silver label. The criteria condense the label definitions and the
intervention rule of relation_extraction/prompts.py; the full guide is about
5,000 tokens and does not fit the lengths Kev trains on.

With --gt100 the input is instead the gt_100 relation test set: its labels joined
to candidates_v4.jsonl, which holds the abstract and every mention of the pair,
the same two files train_relation_evidence.py tests on.

Usage (from the repository root, any Python 3):
    python relation_extraction/decision_models/build_kev_data.py \
        --outdir data/processed/relation/kev_silver
    python relation_extraction/decision_models/build_kev_data.py --gt100 \
        --outdir data/processed/relation/kev_gt_100
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = Path("/home/enes/pathway-re-synth/data/gold")
GT100 = ROOT / "data/processed/gt_100"
GT100_RELATIONS = GT100 / "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable_v4d_single.jsonl"
GT100_CANDIDATES = GT100 / "candidates_v4.jsonl"

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


def request(abstract: str, pathway: tuple, disease: tuple, label: str, meta: dict, prompts) -> dict:
    """pathway and disease are (canonical name, mentions with start/end offsets)."""
    mentions = [
        SimpleNamespace(label=tag, start=m["start"], end=m["end"])
        for tag, (_, spans) in (("PATHWAY", pathway), ("DISEASE", disease))
        for m in spans
    ]
    return {
        "state": {
            "abstract": prompts.mark_abstract(abstract, mentions),
            "pathway": pathway[0],
            "disease": disease[0],
        },
        "questions": {
            "relation": {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": CRITERIA,
                "label": label,
            }
        },
        "_meta": meta,
    }


def to_request(rec: dict, prompts) -> dict:
    return request(
        rec["paragraph"],
        (rec["pathway"]["canonical"], rec["pathway"]["mentions"]),
        (rec["disease"]["canonical"], rec["disease"]["mentions"]),
        rec["class"], {"rid": rec["id"]}, prompts,
    )


def gt100_requests(prompts):
    cands = {}
    for line in open(GT100_CANDIDATES):
        c = json.loads(line)
        cands[c["candidate_id"]] = c
    for line in open(GT100_RELATIONS):
        rel = json.loads(line)
        c = cands[rel["candidate_id"]]
        yield request(
            c["abstract"],
            (c["pathway_key"], c["pathway_mentions"]),
            (c["disease_key"], c["disease_mentions"]),
            rel["label"], {"rid": rel["candidate_id"], "stratum": rel["stratum"]}, prompts,
        )


def write(path: Path, requests) -> None:
    n = 0
    with open(path, "w") as out:
        for req in requests:
            out.write(json.dumps(req, ensure_ascii=False) + "\n")
            n += 1
    print(path.name, n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-dir", type=Path, default=DEFAULT_GOLD,
                    help="directory holding silver_train.jsonl and silver_dev.jsonl")
    ap.add_argument("--gt100", action="store_true",
                    help="write gt_100.jsonl from the gt_100 relation test set instead")
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()

    prompts = load_prompts()
    args.outdir.mkdir(parents=True, exist_ok=True)
    if args.gt100:
        write(args.outdir / "gt_100.jsonl", gt100_requests(prompts))
        return
    for split in ("train", "dev"):
        recs = (json.loads(line) for line in open(args.gold_dir / f"silver_{split}.jsonl"))
        write(args.outdir / f"{split}.jsonl", (to_request(rec, prompts) for rec in recs))


if __name__ == "__main__":
    main()
