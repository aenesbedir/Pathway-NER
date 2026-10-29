"""Extend the 10k + missing split with the sentence-shuffle copies, all in train.

Every PMID of data/processed/pathway-10k-missing/splits.json keeps its
train/val/test assignment, so validation and test are byte-for-byte the sets the
pathway-10k-missing sweep was scored on and the two sweeps differ only in their
training data. The copies written by preprocessing/shuffle_sentence/
shuffle_sentence.py go to train. Each copy's recipient and donor must already be
train PMIDs; a copy built from a validation or test abstract aborts the run,
because its sentences would leak into training.

Usage:
    python scripts/build_shuffle_splits.py \
        --shuffle data/processed/10k-missing-shuffle/k2_n2_seed42/sentence_shuffle.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/processed/pathway-10k-missing/splits.json"
OUT = ROOT / "data/processed/pathway-10k-missing-shuffle/splits.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shuffle", type=Path, required=True,
                    help="sentence_shuffle.jsonl written by shuffle_sentence.py")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    base = json.loads(BASE.read_text())
    train = set(base["train"])
    assigned = train | set(base["val"]) | set(base["test"])

    copies = []
    with args.shuffle.open(encoding="utf-8") as fh:
        for line in fh:
            meta = json.loads(line)["meta"]
            aug = meta["augmentation"]
            for role in ("recipient_pmid", "donor_pmid"):
                if aug[role] not in train:
                    raise SystemExit(f"{meta['pmid']}: {role} {aug[role]} is not a train PMID")
            if meta["pmid"] in assigned:
                raise SystemExit(f"{meta['pmid']} collides with an assigned PMID")
            copies.append(meta["pmid"])
    if len(copies) != len(set(copies)):
        raise SystemExit("duplicate copy ids in the shuffle file")

    out = dict(base)
    # These describe the base corpus, not this one; the dataset meta.json written
    # by tag_bio.py carries the hashes of the merged articles and matches.
    for key in ("articles_sha256", "matches", "matches_sha256"):
        out.pop(key, None)
    out["source"] = (
        "data/processed/pathway-10k-missing/splits.json with the sentence-shuffle "
        "copies appended to train"
    )
    out["base_splits"] = str(BASE.relative_to(ROOT))
    out["base_splits_sha256"] = sha256(BASE)
    out["shuffle"] = str(args.shuffle.resolve().relative_to(ROOT))
    out["shuffle_sha256"] = sha256(args.shuffle)
    out["extension"] = {
        "added": {"train": len(copies), "val": 0, "test": 0},
        "annotation_status": "synthetic",
        "note": "validation and test are those of pathway-10k-missing, unchanged",
    }
    out["train"] = list(base["train"]) + copies
    out["n_pmids"] = sum(len(out[k]) for k in ("train", "val", "test"))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({
        "output": str(args.out),
        "train": len(out["train"]),
        "val": len(out["val"]),
        "test": len(out["test"]),
        "added_to_train": len(copies),
    }, indent=2))


if __name__ == "__main__":
    main()
