"""Merge the curated missing-pathway sample into gt_100, producing gt_125.

gt_100_v2 (scripts/build_gt_100_v2.py) covers only the original 10k corpus. The 25 abstracts curated from the
missing-pathway test split extend the reference to the part of the corpus the
merged dataset added, so a score on gt_125 measures both halves instead of
scoring new training data against an old reference.

Input is the Doccano export of the curation project (admin.jsonl), whose records
carry `entities` with id fields and a `Comments` key; the output keeps only what
gt_100 keeps, so both halves have the same shape and scripts/score_gt_100.py can
read the merged file unchanged.

Usage:
    python scripts/build_gt_125.py --curated <admin.jsonl>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT100 = ROOT / "doccano/golden_dataset/gt_100_v2.jsonl"
OUT = ROOT / "doccano/golden_dataset/gt_125/gt_125.jsonl"
SILVER = ROOT / "doccano/curation/missing_test_sample_25_import.jsonl"



def norm_entities(rec: dict) -> list[dict]:
    out = []
    for e in rec.get("entities") or []:
        if not str(e.get("label", "")).upper().startswith("PATH"):
            continue
        out.append({
            "start_offset": e["start_offset"],
            "end_offset": e["end_offset"],
            "label": "PATHWAY",
        })
    return sorted(out, key=lambda e: (e["start_offset"], e["end_offset"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated", required=True)
    ap.add_argument("--version", required=True,
                    help="label for this curation round, e.g. v2; written to "
                         "gt_125.manifest.json next to the output together with "
                         "the sha256 of the curated export")
    args = ap.parse_args()

    gt = [json.loads(l) for l in GT100.open(encoding="utf-8")]
    gt_pmids = {r["meta"]["pmid"] for r in gt}

    silver = {}
    for line in SILVER.open(encoding="utf-8"):
        rec = json.loads(line)
        silver[rec["meta"]["pmid"]] = rec

    curated = [json.loads(l) for l in Path(args.curated).open(encoding="utf-8")]

    added, n_spans = [], 0
    delta = {"added": 0, "removed": 0, "kept": 0, "moved": 0}
    for rec in curated:
        pmid = rec["meta"]["pmid"]
        if pmid in gt_pmids:
            raise SystemExit(f"{pmid} already in gt_100 - overlap not expected")
        ents = norm_entities(rec)
        n_spans += len(ents)

        sil = silver.get(pmid)
        if sil is not None:
            if sil["text"] != rec["text"]:
                raise SystemExit(f"{pmid}: text changed during curation")
            before = {(s, e) for s, e, _ in sil["label"]}
            after = {(e["start_offset"], e["end_offset"]) for e in ents}
            delta["kept"] += len(before & after)
            delta["added"] += len(after - before)
            delta["removed"] += len(before - after)
            for a in after - before:
                if any(a[0] < b[1] and b[0] < a[1] for b in before - after):
                    delta["moved"] += 1

        added.append({
            "text": rec["text"],
            "entities": ents,
            "meta": {
                "pmid": pmid,
                "source": "missing_pathways test split",
                "query_pathways": rec["meta"].get("query_pathways"),
                "annotation_status": "human_curated",
            },
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for rec in gt:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for rec in added:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    import hashlib

    manifest = {
        "version": args.version,
        "output": str(OUT.relative_to(ROOT)),
        "output_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "curated_export_sha256": hashlib.sha256(Path(args.curated).read_bytes()).hexdigest(),
        "gt_100": str(GT100.relative_to(ROOT)),
        "documents": len(gt) + len(added),
        "curated_documents": len(added),
        "curated_spans": n_spans,
    }
    (OUT.parent / "gt_125.manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")

    gt_spans = sum(
        1 for r in gt for e in r.get("entities", [])
        if str(e.get("label", "")).upper().startswith("PATH")
    )
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "version": args.version,
        "documents": len(gt) + len(added),
        "gt_100_documents": len(gt),
        "gt_100_spans": gt_spans,
        "curated_documents": len(added),
        "curated_spans": n_spans,
        "total_spans": gt_spans + n_spans,
        "curation_delta_vs_silver": delta,
    }, indent=1))


if __name__ == "__main__":
    main()
