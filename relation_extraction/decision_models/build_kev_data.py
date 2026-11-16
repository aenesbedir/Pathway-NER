#!/usr/bin/env python3
"""Turn silver relation pairs into Kev's labelled-request JSONL.

Each pair becomes one request: the abstract with its pathway and disease mentions
marked by prompts.mark_abstract, one `choice` question over the five v4 labels,
and the silver label. The criteria condense the label definitions and the
intervention rule of relation_extraction/prompts.py; the full guide is about
5,000 tokens and does not fit the lengths Kev trains on.

Three inputs:

  default   silver_{train,dev}.jsonl of pathway-re-synth (--gold-dir): the old
            silver_2k_full split, already in that repository's record format.
  --silver  a tracked silver directory such as silver_2k_10kplusmissing: Opus
            labels joined by candidate_id to candidates_same_sentence.jsonl, which
            holds the abstract and every mention of the pair, and split by the
            pmid lists of split_pmids.json in the same directory. Only train and
            dev are written; the test pmids stay closed.
  --gt100   the gt_100 relation test set: its labels joined to
            candidates_v4.jsonl, the same two files train_relation_evidence.py
            tests on.
  --snapshot  a frozen relation silver data product (relation_silver_v1_2026-11-17,
            written by relation_extraction/build_snapshot.py) and an --arm:
              A  silver_2k same_sentence (Opus 4.8) + silver_2k doc_level (Opus 5.5)
              B  A + silver_4k same_sentence (Opus 5.5 / Sonnet 5.5)
                   + silver_4k doc_level_partial (Opus 5.5)
            split by the pmid lists of data/processed/relation/kev_silver_v1/
            split_pmids.json. Dev is the same in both arms: the silver_2k dev
            pmids, both strata. Only train and dev are written.

kev_silver_v1/split_pmids.json is written once with --freeze-snapshot-split. It
keeps every silver_2k pmid where silver_2k_10kplusmissing/split_pmids.json put it,
so dev and test are the old ones plus their doc_level pairs. silver_2k pmids that
only have doc_level pairs, and every silver_4k pmid, go to train: the old split
never saw them, the samples share no pmid and none is a gt_100 pmid, so no pair
leaks. The file records the sha256 of each label and candidate file it covers.

split_pmids.json is written once with --freeze-split from the split_manifest.json
of pathway-re-synth (seed 13, 70/10/20 by abstract over silver_2k_full). That split
only knows abstracts that had a same_sentence pair in silver_2k_full. Abstracts
whose only pairs come from the new pathway spans are added to train: they are
outside dev and test by pmid, so no pair leaks. The file records which pmids were
added and the sha256 of the manifest it came from, and is tracked so machines
without pathway-re-synth (TRUBA, UHEM) build the same split.

Usage (from the repository root, Python 3.7+):
    python relation_extraction/decision_models/build_kev_data.py \
        --outdir data/processed/relation/kev_silver
    python relation_extraction/decision_models/build_kev_data.py \
        --silver data/processed/relation/silver_2k_10kplusmissing \
        --outdir data/processed/relation/kev_silver_10kplusmissing
    python relation_extraction/decision_models/build_kev_data.py --gt100 \
        --outdir data/processed/relation/kev_gt_100
    python relation_extraction/decision_models/build_kev_data.py \
        --silver data/processed/relation/silver_2k_10kplusmissing \
        --freeze-split /home/enes/pathway-re-synth/data/gold/split_manifest.json
    python relation_extraction/decision_models/build_kev_data.py \
        --snapshot /home/enes/artifacts/data-products/relation_silver_v1_2026-11-17 \
        --freeze-snapshot-split
    python relation_extraction/decision_models/build_kev_data.py \
        --snapshot /home/enes/artifacts/data-products/relation_silver_v1_2026-11-17 \
        --arm A --outdir data/processed/relation/kev_silver_v1_A
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD = Path("/home/enes/pathway-re-synth/data/gold")
SILVER_LABELS = "relations_llm_opus48_same_sentence.jsonl"
SILVER_CANDIDATES = "candidates_same_sentence.jsonl"
SPLIT_FILE = "split_pmids.json"
GT100 = ROOT / "data/processed/gt_100"
GT100_RELATIONS = GT100 / "gt_100_disease_pathway_bent-pubmedbert-ner-disease_relation_fable_v4d_single.jsonl"
GT100_CANDIDATES = GT100 / "candidates_v4.jsonl"

# (sample, label file, candidate file) inside the snapshot, per arm.
SNAPSHOT_PARTS = {
    "2k_same": ("silver_2k", "relations_same_sentence.jsonl", "candidates/candidates_same_sentence.jsonl"),
    "2k_doc": ("silver_2k", "relations_doc_level.jsonl", "candidates/candidates_doc_level.jsonl"),
    "4k_same": ("silver_4k", "relations_same_sentence.jsonl", "candidates/candidates_same_sentence.jsonl"),
    "4k_doc": ("silver_4k", "relations_doc_level_partial.jsonl", "candidates/candidates_doc_level.jsonl"),
}
ARMS = {"A": ["2k_same", "2k_doc"], "B": ["2k_same", "2k_doc", "4k_same", "4k_doc"]}
SNAPSHOT_SPLIT = ROOT / "data/processed/relation/kev_silver_v1/split_pmids.json"
OLD_SPLIT = ROOT / "data/processed/relation/silver_2k_10kplusmissing" / SPLIT_FILE

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


def read_jsonl(path: Path) -> list:
    with open(path) as fh:
        return [json.loads(line) for line in fh]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_split(silver: Path, manifest_path: Path) -> None:
    """Write split_pmids.json: the manifest's pmid split, unsplit pmids added to train."""
    manifest = json.loads(manifest_path.read_text())
    split = {name: sorted(pmids) for name, pmids in manifest["split_pmids"].items()}
    known = {pmid for pmids in split.values() for pmid in pmids}
    labelled = {rec["pmid"] for rec in read_jsonl(silver / SILVER_LABELS)}
    added = sorted(labelled - known)
    split["train"] = sorted(split["train"] + added)
    out = {
        "what": "pmid split of the silver relation pairs for Kev fine-tuning",
        "source_manifest": str(manifest_path),
        "source_manifest_sha256": sha256(manifest_path),
        "split_seed": manifest.get("split_seed"),
        "split_ratios": manifest.get("split_ratios"),
        "labels": SILVER_LABELS,
        "labels_sha256": sha256(silver / SILVER_LABELS),
        "added_to_train": added,
        "added_to_train_note": "labelled pmids absent from the source split: their only "
                               "same_sentence pairs come from the new pathway spans",
        "split_pmids": split,
    }
    (silver / SPLIT_FILE).write_text(json.dumps(out, indent=2) + "\n")
    print(SPLIT_FILE, {name: len(pmids) for name, pmids in split.items()}, "added", len(added))


def silver_requests(silver: Path, prompts) -> dict:
    """{split: requests} for train and dev; the test pmids are not read."""
    split_doc = json.loads((silver / SPLIT_FILE).read_text())
    if split_doc["labels_sha256"] != sha256(silver / SILVER_LABELS):
        raise SystemExit(f"{SILVER_LABELS} changed since {SPLIT_FILE} was frozen")
    of_pmid = {pmid: name for name, pmids in split_doc["split_pmids"].items() for pmid in pmids}
    cands = {c["candidate_id"]: c for c in read_jsonl(silver / SILVER_CANDIDATES)}
    out = {"train": [], "dev": []}
    for rel in read_jsonl(silver / SILVER_LABELS):
        name = of_pmid.get(rel["pmid"])
        if name is None:
            raise SystemExit(f"pmid {rel['pmid']} is in no split; refreeze {SPLIT_FILE}")
        if name not in out:
            continue
        c = cands[rel["candidate_id"]]
        out[name].append(request(
            c["abstract"],
            (c["pathway_key"], c["pathway_mentions"]),
            (c["disease_key"], c["disease_mentions"]),
            rel["label"],
            {"rid": rel["candidate_id"], "pmid": rel["pmid"], "stratum": rel["stratum"]},
            prompts,
        ))
    for name, reqs in out.items():
        labels = Counter(r["questions"]["relation"]["label"] for r in reqs)
        print(name, len(reqs), "pairs", len({r["_meta"]["pmid"] for r in reqs}), "abstracts", dict(labels))
    return out


def snapshot_files(snapshot: Path, part: str) -> tuple:
    sample, labels, candidates = SNAPSHOT_PARTS[part]
    return snapshot / sample / labels, snapshot / sample / candidates


def freeze_snapshot_split(snapshot: Path) -> None:
    """Write kev_silver_v1/split_pmids.json from the old silver_2k split."""
    old = json.loads(OLD_SPLIT.read_text())
    of_pmid = {pmid: name for name, pmids in old["split_pmids"].items() for pmid in pmids}
    gt100_pmids = {str(json.loads(line)["pmid"]) for line in open(GT100_CANDIDATES)}

    pmids = {}
    files = {}
    for part in SNAPSHOT_PARTS:
        labels, candidates = snapshot_files(snapshot, part)
        pmids[part] = {str(rec["pmid"]) for rec in read_jsonl(labels)}
        for path in (labels, candidates):
            files[str(path.relative_to(snapshot))] = sha256(path)
    pmids_2k = pmids["2k_same"] | pmids["2k_doc"]
    pmids_4k = pmids["4k_same"] | pmids["4k_doc"]
    if pmids_2k & pmids_4k:
        raise SystemExit(f"silver_2k and silver_4k share {len(pmids_2k & pmids_4k)} pmids")
    if (pmids_2k | pmids_4k) & gt100_pmids:
        raise SystemExit("silver pmids overlap gt_100")
    missing = pmids["2k_same"] - of_pmid.keys()
    if missing:
        raise SystemExit(f"{len(missing)} silver_2k same_sentence pmids are not in {OLD_SPLIT}")

    split = {name: set(p for p in pmids_2k if of_pmid.get(p) == name) for name in ("train", "dev", "test")}
    doc_only_2k = sorted(pmids_2k - of_pmid.keys())
    split["train"] |= set(doc_only_2k) | pmids_4k
    out = {
        "what": "pmid split of the relation_silver_v1 pairs for Kev fine-tuning (arms A and B)",
        "snapshot": snapshot.name,
        "snapshot_files_sha256": files,
        "source_split": str(OLD_SPLIT.relative_to(ROOT)),
        "source_split_sha256": sha256(OLD_SPLIT),
        "rule": "silver_2k pmids keep their place in source_split (seed 13, 70/10/20 by abstract); "
                "silver_2k pmids absent from it (only doc_level pairs) and all silver_4k pmids go to train",
        "added_to_train_silver_2k_doc_only": doc_only_2k,
        "added_to_train_silver_4k": sorted(pmids_4k),
        "split_pmids": {name: sorted(p) for name, p in split.items()},
    }
    SNAPSHOT_SPLIT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_SPLIT.write_text(json.dumps(out, indent=2) + "\n")
    print(SNAPSHOT_SPLIT.relative_to(ROOT), {name: len(p) for name, p in split.items()},
          "silver_2k doc-only added", len(doc_only_2k), "silver_4k added", len(pmids_4k))


def snapshot_requests(snapshot: Path, arm: str, prompts) -> dict:
    """{split: requests} for train and dev of one arm; the test pmids are not read."""
    split_doc = json.loads(SNAPSHOT_SPLIT.read_text())
    if split_doc["snapshot"] != snapshot.name:
        raise SystemExit(f"{SNAPSHOT_SPLIT} was frozen for {split_doc['snapshot']}, not {snapshot.name}")
    of_pmid = {pmid: name for name, pmids in split_doc["split_pmids"].items() for pmid in pmids}
    out = {"train": [], "dev": []}
    for part in ARMS[arm]:
        labels, candidates = snapshot_files(snapshot, part)
        for path in (labels, candidates):
            rel = str(path.relative_to(snapshot))
            if split_doc["snapshot_files_sha256"][rel] != sha256(path):
                raise SystemExit(f"{rel} changed since {SNAPSHOT_SPLIT.name} was frozen")
        wanted = {}
        for rec in read_jsonl(labels):
            name = of_pmid.get(str(rec["pmid"]))
            if name is None:
                raise SystemExit(f"pmid {rec['pmid']} is in no split; refreeze {SNAPSHOT_SPLIT.name}")
            if name in out:
                wanted[rec["candidate_id"]] = (name, rec)
        found = 0
        for line in open(candidates):
            c = json.loads(line)
            if c["candidate_id"] not in wanted:
                continue
            found += 1
            name, rec = wanted[c["candidate_id"]]
            out[name].append(request(
                c["abstract"],
                (c["pathway_key"], c["pathway_mentions"]),
                (c["disease_key"], c["disease_mentions"]),
                rec["label"],
                {"rid": rec["candidate_id"], "pmid": str(rec["pmid"]), "stratum": rec["stratum"],
                 "part": part, "relation_source": rec["relation_source"]},
                prompts,
            ))
        if found != len(wanted):
            raise SystemExit(f"{part}: {len(wanted) - found} labelled pairs have no candidate")
    for name, reqs in out.items():
        for stratum in ("same_sentence", "doc_level"):
            sub = [r for r in reqs if r["_meta"]["stratum"] == stratum]
            labels = Counter(r["questions"]["relation"]["label"] for r in sub)
            print(arm, name, stratum, len(sub), "pairs", len({r["_meta"]["pmid"] for r in sub}),
                  "abstracts", dict(labels))
    return out


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
    ap.add_argument("--silver", type=Path,
                    help="tracked silver directory holding split_pmids.json; writes train.jsonl and dev.jsonl")
    ap.add_argument("--freeze-split", type=Path, metavar="SPLIT_MANIFEST",
                    help="with --silver: write its split_pmids.json from this pathway-re-synth manifest")
    ap.add_argument("--snapshot", type=Path,
                    help="relation silver data product; with --arm writes train.jsonl and dev.jsonl")
    ap.add_argument("--arm", choices=sorted(ARMS))
    ap.add_argument("--freeze-snapshot-split", action="store_true",
                    help=f"with --snapshot: write {SNAPSHOT_SPLIT.relative_to(ROOT)}")
    ap.add_argument("--outdir", type=Path)
    args = ap.parse_args()

    if args.freeze_snapshot_split:
        if not args.snapshot:
            ap.error("--freeze-snapshot-split needs --snapshot")
        freeze_snapshot_split(args.snapshot.resolve())
        return
    if args.freeze_split:
        if not args.silver:
            ap.error("--freeze-split needs --silver")
        freeze_split(args.silver, args.freeze_split)
        return
    if not args.outdir:
        ap.error("--outdir is required")
    prompts = load_prompts()
    args.outdir.mkdir(parents=True, exist_ok=True)
    if args.gt100:
        write(args.outdir / "gt_100.jsonl", gt100_requests(prompts))
        return
    if args.snapshot:
        if not args.arm:
            ap.error("--snapshot needs --arm")
        for name, reqs in snapshot_requests(args.snapshot.resolve(), args.arm, prompts).items():
            write(args.outdir / f"{name}.jsonl", reqs)
        return
    if args.silver:
        for name, reqs in silver_requests(args.silver, prompts).items():
            write(args.outdir / f"{name}.jsonl", reqs)
        return
    for split in ("train", "dev"):
        recs = (json.loads(line) for line in open(args.gold_dir / f"silver_{split}.jsonl"))
        write(args.outdir / f"{split}.jsonl", (to_request(rec, prompts) for rec in recs))


if __name__ == "__main__":
    main()
