"""Extend the frozen 10k split with the 775 missing-pathway abstracts.

The 10,125 PMIDs of data/processed/pathway-10k/splits.json keep their existing
train/val/test assignment untouched, so every earlier result on this corpus stays
comparable and the 100 gt_100 abstracts remain in test where they were. The 775
new PMIDs are shuffled once at SEED and appended 625/75/75.

Note that the 75 new test PMIDs are LLM-reviewed silver, while the rest of test
is reviewed annotation; a test score on the extended split therefore measures a
mixture and is not directly comparable to a score on the old test set. Score
against the gt_100 subset when comparing to earlier runs.

Usage:
    python scripts/build_merged_splits.py
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/processed/pathway-10k/splits.json"
MERGED = ROOT / "data/doccano/pathway_10k_plus_missing.jsonl"
OUT = ROOT / "data/processed/pathway-10k-missing/splits.json"

SEED = 42
ADD = {"train": 625, "val": 75, "test": 75}


def main() -> None:
    base = json.loads(BASE.read_text())
    assigned = {p for k in ("train", "val", "test") for p in base[k]}

    new = []
    seen = set()
    for line in MERGED.open(encoding="utf-8"):
        pmid = json.loads(line)["meta"]["pmid"]
        if pmid in assigned or pmid in seen:
            continue
        seen.add(pmid)
        new.append(pmid)

    total = sum(ADD.values())
    if len(new) != total:
        raise SystemExit(f"expected {total} new pmids, found {len(new)}")

    random.Random(SEED).shuffle(new)
    cut_train = ADD["train"]
    cut_val = cut_train + ADD["val"]
    added = {
        "train": new[:cut_train],
        "val": new[cut_train:cut_val],
        "test": new[cut_val:],
    }

    out = dict(base)
    out["source"] = (
        "data/processed/pathway-10k/splits.json extended with the missing-pathway "
        "abstracts of data/doccano/pathway_10k_plus_missing.jsonl"
    )
    out["matches"] = str(MERGED.relative_to(ROOT))
    out["matches_sha256"] = hashlib.sha256(MERGED.read_bytes()).hexdigest()
    out["base_splits"] = str(BASE.relative_to(ROOT))
    out["extension"] = {
        "seed": SEED,
        "added": {k: len(v) for k, v in added.items()},
        "annotation_status": "llm_reviewed_silver",
        "note": (
            "the 10,125 original pmids keep their assignment; gt_100 stays in test"
        ),
    }
    for k in ("train", "val", "test"):
        out[k] = list(base[k]) + added[k]
    out["n_pmids"] = sum(len(out[k]) for k in ("train", "val", "test"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")

    gt = {json.loads(l)["meta"]["pmid"] for l in
          (ROOT / "doccano/golden_dataset/gt_100.jsonl").open(encoding="utf-8")}
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "train": len(out["train"]),
        "val": len(out["val"]),
        "test": len(out["test"]),
        "total": out["n_pmids"],
        "added": out["extension"]["added"],
        "gt_100_in_test": len(gt & set(out["test"])),
    }, indent=1))


if __name__ == "__main__":
    main()
