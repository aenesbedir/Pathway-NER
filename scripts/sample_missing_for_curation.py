"""Sample missing-pathway test abstracts for manual curation in Doccano.

The 775 new abstracts of pathway_10k_plus_missing.jsonl carry silver labels: the
NER checkpoint, the pattern booster and the surface-form dictionary merged, with
the spans an LLM audit called wrong removed. 75 of them landed in the test split,
where silver labels are worth least - a test score is only as good as its
reference. This script draws a random sample of them for human curation, so the
curated result can be folded into gt_100 and the sweep re-scored against a
reference that covers the new corpus as well as the old.

Two files are written, because Doccano reads one shape and writes another:

  *_import.jsonl  {"text": ..., "label": [[start, end, "PATHWAY"], ...], "meta": {...}}
      The sequence-labeling import shape, the same one data/doccano/*.jsonl use.
      `meta` holds only scalars and strings; nested objects break the importer.

  *_reference.jsonl  {"text": ..., "entities": [{"start_offset", ...}], "meta": {...}}
      The export shape that doccano/golden_dataset/gt_100.jsonl uses, kept so the
      sample can be diffed against gt_100 and merged into it later.

The existing silver spans are pre-filled, so curation is accept / fix / delete /
add rather than annotation from scratch. meta.silver spells out which stage
produced each span, as one readable line per span.

Usage:
    python scripts/sample_missing_for_curation.py --n 25 --seed 11
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGED = ROOT / "data/doccano/pathway_10k_plus_missing.jsonl"
SPLITS = ROOT / "data/processed/pathway-10k-missing/splits.json"
STAGES = ROOT / "data/processed/missing_pathways/missing_llm_review.jsonl"
OUT_DIR = ROOT / "doccano/curation"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    splits = json.loads(SPLITS.read_text())
    test = set(splits["test"])
    added_test = set(splits["test"][-splits["extension"]["added"]["test"]:])
    if not added_test <= test:
        raise SystemExit("extension pmids are not a suffix of the test split")

    stages = {}
    for line in STAGES.open(encoding="utf-8"):
        rec = json.loads(line)
        stages[rec["pmid"]] = rec

    docs = {}
    for line in MERGED.open(encoding="utf-8"):
        doc = json.loads(line)
        pmid = doc["meta"]["pmid"]
        if pmid in added_test:
            docs[pmid] = doc

    if len(docs) != len(added_test):
        raise SystemExit(f"{len(docs)} of {len(added_test)} test pmids found")

    import random

    pmids = sorted(docs)
    random.Random(args.seed).shuffle(pmids)
    picked = sorted(pmids[: args.n])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    imp = OUT_DIR / f"missing_test_sample_{args.n}_import.jsonl"
    ref = OUT_DIR / f"missing_test_sample_{args.n}_reference.jsonl"
    n_spans = 0
    with imp.open("w", encoding="utf-8") as fi, ref.open("w", encoding="utf-8") as fr:
        for pmid in picked:
            doc = docs[pmid]
            text = doc["text"]
            label = [[s, e, "PATHWAY"] for s, e, _ in doc["label"]]
            n_spans += len(label)
            st = stages.get(pmid, {})
            silver = "; ".join(
                f"{s['text']} [{s['source']}"
                + (f" -> {s['canonical']}]" if s.get("canonical") else "]")
                for s in st.get("spans", [])
            )
            meta = {
                "pmid": pmid,
                "source": "missing_pathways test split",
                "query_pathways": ", ".join(st.get("pathways") or []),
                "route": st.get("route") or "",
                "annotation_status": "silver_for_curation",
                "silver": silver,
            }
            fi.write(json.dumps({"text": text, "label": label, "meta": meta},
                                ensure_ascii=False) + "\n")
            fr.write(json.dumps({
                "text": text,
                "entities": [
                    {"start_offset": s, "end_offset": e, "label": "PATHWAY"}
                    for s, e, _ in doc["label"]
                ],
                "meta": meta,
            }, ensure_ascii=False) + "\n")

    print(json.dumps({
        "import_file": str(imp.relative_to(ROOT)),
        "reference_file": str(ref.relative_to(ROOT)),
        "documents": len(picked),
        "pre_filled_spans": n_spans,
        "docs_without_span": sum(1 for p in picked if not docs[p]["label"]),
        "sampled_from": len(added_test),
        "seed": args.seed,
    }, indent=1))


if __name__ == "__main__":
    main()
